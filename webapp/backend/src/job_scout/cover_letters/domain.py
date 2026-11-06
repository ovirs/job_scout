"""Cover Letters: the letter the user sends with one Application, written as drafts.

An Application has at most one Cover Letter, and the latest live draft is it. The LLM
writes drafts on request while the Application is Preparing, from the posting, the
Career Profile, the Writing Guide and the flags of the Evaluation the user agreed to,
from scratch or revising the latest draft in words; each request is its own row, and a
failed one leaves the letter as it was. The user also saves hand edits as drafts, restores
an earlier draft as a new one and deletes drafts, keeping them. Outside Preparing the
letter is locked, and the latest draft on each move to Applied is the letter sent.

Each operation enforces these rules and refuses with a `Refused` error otherwise; an
unknown Application or draft raises `NoSuchApplication` or `NoSuchDraft`.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import procrastinate
from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from job_scout.applications import domain as applications
from job_scout.applications.models import Application, ApplicationStateChange
from job_scout.cover_letters.generation import locked_reason, missing_input
from job_scout.cover_letters.models import CoverLetterDraft, CoverLetterGeneration, EvaluationCase
from job_scout.cover_letters.tasks import GENERATION
from job_scout.evaluations import domain as evaluations
from job_scout.evaluations.models import Evaluation
from job_scout.llm_runs import domain as llm_runs
from job_scout.user_inputs import domain as user_inputs


class NoSuchApplication(Exception):
    """The owner has no live Application with this id."""


class NoSuchDraft(Exception):
    """The Application has no live draft with this id."""


class Refused(Exception):
    """The Cover Letter's rules refuse the operation; the message says why."""


class Locked(Refused):
    """The Cover Letter changes only while the Application is Preparing."""


class MissingInput(Refused):
    """There is no Career Profile to write the letter from."""


class WrongEvaluationCase(Refused):
    """The user confirmed another case than the posting's Evaluation is in now."""


class NothingToRevise(Refused):
    """A revision in words needs a draft to revise."""


class GenerationUnderWay(Refused):
    """Another generation is under way, and not stuck."""


@dataclass(frozen=True)
class FlagsSource:
    """Which Evaluation a letter generated now would take its flags from, and its case."""

    case: EvaluationCase
    evaluation: Evaluation | None  # None exactly when the case is missing


@dataclass(frozen=True)
class SentLetter:
    """The letter sent on the Application's latest move to Applied."""

    applied_at: datetime
    draft: CoverLetterDraft | None  # None when no letter was sent


@dataclass(frozen=True)
class CoverLetter:
    """An Application's Cover Letter as the user sees it."""

    application: Application
    drafts: list[CoverLetterDraft]  # every live draft, the latest first
    sent: SentLetter | None  # None until the Application first moves to Applied
    generation: CoverLetterGeneration | None  # the latest request, whatever became of it
    flags_source: FlagsSource  # what generating now would take flags from

    @property
    def draft(self) -> CoverLetterDraft | None:
        """The letter: its latest live draft, if it has one."""
        return self.drafts[0] if self.drafts else None

    @property
    def editable(self) -> bool:
        return locked_reason(self.application) is None

    @property
    def posting_edited_since_draft(self) -> bool | None:
        """Whether the posting's text changed since the latest draft; None with no draft."""
        if self.draft is None:
            return None
        return self.draft.content_hash != self.application.job_posting.content_hash


async def read(session: AsyncSession, *, owner_id: uuid.UUID, application_id: int) -> CoverLetter:
    """The Application's Cover Letter. Raises `NoSuchApplication`."""
    return await _letter(session, await _application(session, owner_id, application_id))


async def generate(
    session: AsyncSession,
    task_queue: procrastinate.App,
    *,
    owner_id: uuid.UUID,
    application_id: int,
    evaluation_case: EvaluationCase,
    instruction: str | None,
) -> CoverLetter:
    """Queue a new draft written by the LLM from scratch; also the retry of a failed one.

    Refused unless the Application is Preparing, while there is no Career Profile, when
    `evaluation_case` is not the Evaluation's case now (the user must confirm a missing
    or outdated one), and while another request is under way, unless that one is stuck:
    it is then failed and replaced.
    """
    application = await _editable(session, owner_id, application_id)
    await _queue(session, task_queue, application, evaluation_case, instruction, None)
    return await _letter(session, application)


async def revise(
    session: AsyncSession,
    task_queue: procrastinate.App,
    *,
    owner_id: uuid.UUID,
    application_id: int,
    evaluation_case: EvaluationCase,
    instruction: str,
) -> CoverLetter:
    """Queue a revision in words of the latest draft, hand edits included: the LLM gets
    its text and the instruction with the same inputs as generating. Refused as
    generating is, and while there is no draft to revise."""
    application = await _editable(session, owner_id, application_id)
    latest = await _latest_draft(session, application)
    if latest is None:
        raise NothingToRevise("There is no draft to revise: generate or write one first")
    await _queue(session, task_queue, application, evaluation_case, instruction, latest)
    return await _letter(session, application)


async def save(
    session: AsyncSession, *, owner_id: uuid.UUID, application_id: int, text: str
) -> CoverLetter:
    """Save the user's hand edit as the new latest draft; the earlier drafts are kept.
    Refused unless the Application is Preparing.

    The draft keeps the unsupported requirements of the draft it edits, which are about
    the posting and the profile, not the wording, and that draft's posting content hash,
    since its text was written against the posting then; a draft from nothing takes the
    posting's now.
    """
    application = await _editable(session, owner_id, application_id)
    latest = await _latest_draft(session, application)
    session.add(
        CoverLetterDraft(
            owner_id=application.owner_id,
            application_id=application.id,
            origin="edited_by_hand",
            text=text,
            created_at=datetime.now(UTC),
            unsupported_requirements=[] if latest is None else latest.unsupported_requirements,
            content_hash=application.job_posting.content_hash
            if latest is None
            else latest.content_hash,
        )
    )
    await session.commit()
    return await _letter(session, application)


async def restore(
    session: AsyncSession, *, owner_id: uuid.UUID, application_id: int, draft_id: int
) -> CoverLetter:
    """Make an earlier draft the letter again: a new latest draft copies its text and its
    whole record, and points back to it. Refused unless the Application is Preparing;
    raises `NoSuchDraft` for a draft not live on the Application."""
    application = await _editable(session, owner_id, application_id)
    draft = await _draft(session, application, draft_id)
    session.add(
        CoverLetterDraft(
            owner_id=draft.owner_id,
            application_id=draft.application_id,
            origin=draft.origin,
            text=draft.text,
            instruction=draft.instruction,
            unsupported_requirements=draft.unsupported_requirements,
            model=draft.model,
            prompt_version=draft.prompt_version,
            career_profile_version_id=draft.career_profile_version_id,
            writing_guide_version_id=draft.writing_guide_version_id,
            evaluation_id=draft.evaluation_id,
            evaluation_case=draft.evaluation_case,
            content_hash=draft.content_hash,
            restored_from_draft_id=draft.id,
            created_at=datetime.now(UTC),
        )
    )
    await session.commit()
    return await _letter(session, application)


async def delete(
    session: AsyncSession, *, owner_id: uuid.UUID, application_id: int, draft_id: int
) -> CoverLetter:
    """Delete a draft, keeping it: hidden from the letter and its drafts, and the draft
    before it is the letter again. A letter already sent stays the one sent. Refused
    unless the Application is Preparing; raises `NoSuchDraft` for a draft not live on
    the Application."""
    application = await _editable(session, owner_id, application_id)
    draft = await _draft(session, application, draft_id)
    draft.deleted_at = datetime.now(UTC)
    await session.commit()
    return await _letter(session, application)


async def _application(
    session: AsyncSession, owner_id: uuid.UUID, application_id: int, *, for_update: bool = False
) -> Application:
    found = await applications.application(
        session, owner_id=owner_id, application_id=application_id, for_update=for_update
    )
    if found is None:
        raise NoSuchApplication
    return found


async def _editable(session: AsyncSession, owner_id: uuid.UUID, application_id: int) -> Application:
    """The Application, if its Cover Letter can change now, locked until the transaction
    ends: one change at a time, and none while the Application moves."""
    application = await _application(session, owner_id, application_id, for_update=True)
    if locked_reason(application) is not None:
        raise Locked(
            "The Cover Letter is locked: it changes only while the Application is Preparing"
        )
    return application


async def _queue(
    session: AsyncSession,
    task_queue: procrastinate.App,
    application: Application,
    evaluation_case: EvaluationCase,
    instruction: str | None,
    revised: CoverLetterDraft | None,
) -> None:
    """Queue a generation, a revision in words of `revised` when given."""
    profile = await user_inputs.current_document(
        session, owner_id=application.owner_id, kind="career-profile"
    )
    missing = missing_input(profile)
    if missing is not None:
        raise MissingInput(missing)
    source = await _flags_source(session, application)
    if evaluation_case != source.case:
        raise WrongEvaluationCase(
            f"The posting's Evaluation is {source.case}, not {evaluation_case}: "
            "confirm that case to generate"
        )
    under_way = await session.scalars(
        select(CoverLetterGeneration).where(
            CoverLetterGeneration.application_id == application.id,
            CoverLetterGeneration.status.in_(llm_runs.UNDER_WAY),
        )
    )
    try:
        llm_runs.clear_the_way(list(under_way))
    except llm_runs.RunUnderWay:
        raise GenerationUnderWay("A draft is already being written for this Cover Letter") from None
    queued = CoverLetterGeneration(
        owner_id=application.owner_id,
        application_id=application.id,
        status="queued",
        instruction=instruction,
        evaluation_id=None if source.evaluation is None else source.evaluation.id,
        evaluation_case=source.case,
        revised_draft=revised,
    )
    session.add(queued)
    await llm_runs.commit_and_enqueue(session, task_queue, GENERATION, queued)


async def _flags_source(session: AsyncSession, application: Application) -> FlagsSource:
    """The posting's current Evaluation, if it has one, and whether it is outdated."""
    posting = application.job_posting
    runs = await evaluations.history(session, owner_id=posting.owner_id, job_posting_id=posting.id)
    current = evaluations.current(runs)
    if current is None:
        return FlagsSource("missing", None)
    return FlagsSource("outdated" if evaluations.outdated(current, posting) else "current", current)


async def _draft(
    session: AsyncSession, application: Application, draft_id: int
) -> CoverLetterDraft:
    found = await session.scalar(_live_drafts(application).where(CoverLetterDraft.id == draft_id))
    if found is None:
        raise NoSuchDraft
    return found


async def _latest_draft(session: AsyncSession, application: Application) -> CoverLetterDraft | None:
    return await session.scalar(_live_drafts(application).limit(1))


def _live_drafts(application: Application) -> Select[CoverLetterDraft]:
    """The Application's drafts not deleted, the latest first."""
    return (
        select(CoverLetterDraft)
        .where(
            CoverLetterDraft.application_id == application.id,
            CoverLetterDraft.deleted_at.is_(None),
        )
        .order_by(CoverLetterDraft.id.desc())
    )


async def _letter(session: AsyncSession, application: Application) -> CoverLetter:
    return CoverLetter(
        application=application,
        drafts=list(await session.scalars(_live_drafts(application))),
        sent=await _sent(session, application),
        generation=await session.scalar(
            select(CoverLetterGeneration)
            .where(CoverLetterGeneration.application_id == application.id)
            .order_by(CoverLetterGeneration.id.desc())
            .limit(1)
        ),
        flags_source=await _flags_source(session, application),
    )


async def _sent(session: AsyncSession, application: Application) -> SentLetter | None:
    """The letter sent on the latest move to Applied: the latest draft made before it and
    not deleted by then. No draft is made or deleted while the letter is locked, so this
    is the letter as it was when the Application moved, even if its draft is deleted
    after a move back to Preparing.

    The times compared are all taken by the app, each while holding the Application's
    lock, so a draft stored just before a move is always made before it."""
    applied = _latest_move_to_applied(application)
    if applied is None:
        return None
    draft = await session.scalar(
        select(CoverLetterDraft)
        .where(
            CoverLetterDraft.application_id == application.id,
            CoverLetterDraft.created_at < applied.changed_at,
            or_(
                CoverLetterDraft.deleted_at.is_(None),
                CoverLetterDraft.deleted_at > applied.changed_at,
            ),
        )
        .order_by(CoverLetterDraft.id.desc())
        .limit(1)
    )
    return SentLetter(applied_at=applied.changed_at, draft=draft)


def _latest_move_to_applied(application: Application) -> ApplicationStateChange | None:
    return next((c for c in reversed(application.history) if c.state == "applied"), None)
