"""Cover Letters: the letter the user sends with one Application, written as drafts.

An Application has at most one Cover Letter, and the latest live draft is it. The LLM
writes drafts on request while the Application is Preparing, from the posting, the
Career Profile, the Writing Guide and the flags of the Evaluation the user agreed to,
from scratch or revising the latest draft in words; each request is its own row, and a
failed one leaves the letter as it was. The user also saves hand edits as drafts, restores
an earlier draft as a new one and deletes drafts, keeping them. Outside Preparing the
letter is locked, and each move to Applied records the latest draft as the letter sent.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from job_scout import cover_letter, evaluations, user_inputs
from job_scout.cover_letter import CoverLetterPrompt, CoverLetterResult, Flags
from job_scout.evaluation import PostingText
from job_scout.llm import Failure, Outcome
from job_scout.models import (
    Application,
    ApplicationStateChange,
    CoverLetterDraft,
    CoverLetterGeneration,
    CoverLetterGenerationFailureKind,
    DocumentVersion,
    Evaluation,
    EvaluationCase,
    JobPosting,
)


@dataclass(frozen=True)
class FlagsSource:
    """Which Evaluation a letter generated now would take its flags from, and its case."""

    case: EvaluationCase
    evaluation: Evaluation | None  # None exactly when the case is missing


async def flags_source(session: AsyncSession, application: Application) -> FlagsSource:
    """The posting's current Evaluation, if it has one, and whether it is outdated."""
    posting = application.job_posting
    runs = await evaluations.history(session, owner_id=posting.owner_id, job_posting_id=posting.id)
    current = evaluations.current(runs)
    if current is None:
        return FlagsSource("missing", None)
    return FlagsSource("outdated" if evaluations.outdated(current, posting) else "current", current)


def queued(
    application: Application,
    source: FlagsSource,
    instruction: str | None,
    revised: CoverLetterDraft | None = None,
) -> CoverLetterGeneration:
    """A new queued generation for the Application, a revision in words of `revised` when
    given; the caller enqueues its task."""
    return CoverLetterGeneration(
        owner_id=application.owner_id,
        application_id=application.id,
        status="queued",
        instruction=instruction,
        evaluation_id=None if source.evaluation is None else source.evaluation.id,
        evaluation_case=source.case,
        revised_draft=revised,
    )


@dataclass(frozen=True)
class Inputs:
    """What one run of a generation is made from: the user inputs current when it ran,
    the posting's text then, and the flags of the Evaluation fixed at the request, with
    its case judged against that text."""

    career_profile: DocumentVersion | None
    writing_guide: DocumentVersion | None
    posting: PostingText
    content_hash: str
    flags: Flags | None
    # An Evaluation current at the request is outdated if the posting changed since
    evaluation_case: EvaluationCase
    revised_text: str | None  # the draft a revision in words revises, as it was requested
    instruction: str | None

    def missing(self) -> str | None:
        """Why there is nothing to write the letter from, if there is not."""
        return missing_input(self.career_profile)

    def prompt(self) -> CoverLetterPrompt:
        assert self.career_profile is not None
        return cover_letter.prompt(
            career_profile=self.career_profile.text,
            writing_guide=None if self.writing_guide is None else self.writing_guide.text,
            posting=self.posting,
            flags=self.flags,
            draft=self.revised_text,
            instruction=self.instruction,
        )


def editable(application: Application) -> bool:
    """Whether the Application's Cover Letter takes new drafts: only while it is Preparing."""
    return application.deleted_at is None and application.state == "preparing"


def missing_input(career_profile: DocumentVersion | None) -> str | None:
    """Why there is nothing to write a Cover Letter from, if there is not; the Career
    Profile is the only input required."""
    if career_profile is None or not career_profile.text.strip():
        return "There is no Career Profile to write the Cover Letter from: write it first"
    return None


async def start(session: AsyncSession, generation: CoverLetterGeneration) -> Inputs:
    """Mark the generation running and gather what it is made from."""
    generation.status = "running"
    generation.started_at = generation.started_at or datetime.now(UTC)
    application = await session.get_one(Application, generation.application_id)
    posting: JobPosting = application.job_posting
    owner_id = generation.owner_id
    flags = None
    case: EvaluationCase = "missing"
    if generation.evaluation_id is not None:
        run = await session.get_one(Evaluation, generation.evaluation_id)
        result = evaluations.checked_result(run)
        assert result is not None
        flags = Flags(
            green=[flag.point for flag in result.green_flags],
            red=[flag.point for flag in result.red_flags],
        )
        case = "outdated" if evaluations.outdated(run, posting) else "current"
    return Inputs(
        career_profile=await user_inputs.current_document(
            session, owner_id=owner_id, kind="career-profile"
        ),
        writing_guide=await user_inputs.current_document(
            session, owner_id=owner_id, kind="writing-guide"
        ),
        posting=PostingText(
            title=posting.title,
            company=posting.company,
            location_text=posting.location_text,
            description=posting.description,
        ),
        content_hash=posting.content_hash,
        flags=flags,
        evaluation_case=case,
        revised_text=None if generation.revised_draft is None else generation.revised_draft.text,
        instruction=generation.instruction,
    )


def check(outcome: Outcome[CoverLetterResult]) -> Outcome[CoverLetterResult]:
    """The call's outcome with its result checked; a blank letter becomes a malformed
    failure."""
    result = outcome.result
    if not isinstance(result, Failure) and not result.letter.strip():
        return Outcome(
            result=Failure("malformed", "The answer's letter is blank"),
            model=outcome.model,
            prompt_version=outcome.prompt_version,
        )
    return outcome


def record(
    session: AsyncSession,
    generation: CoverLetterGeneration,
    inputs: Inputs,
    outcome: Outcome[CoverLetterResult],
) -> None:
    """Store a run's outcome: done with a new generated draft, or failed with no draft."""
    result = outcome.result
    if isinstance(result, Failure):
        record_failure(generation, result.kind, result.reason)
        return
    draft = CoverLetterDraft(
        owner_id=generation.owner_id,
        application_id=generation.application_id,
        origin="generated" if generation.revised_draft_id is None else "revised_in_words",
        text=result.letter,
        instruction=generation.instruction,
        unsupported_requirements=result.unsupported_requirements,
        model=outcome.model,
        prompt_version=outcome.prompt_version,
        career_profile_version_id=_id(inputs.career_profile),
        writing_guide_version_id=_id(inputs.writing_guide),
        evaluation_id=generation.evaluation_id,
        evaluation_case=inputs.evaluation_case,
        content_hash=inputs.content_hash,
    )
    session.add(draft)
    generation.status = "done"
    generation.finished_at = datetime.now(UTC)
    generation.failure_kind = generation.failure_reason = None
    generation.draft = draft


def record_failure(
    generation: CoverLetterGeneration, kind: CoverLetterGenerationFailureKind, reason: str
) -> None:
    """Store a run that made no draft; the Cover Letter stays as it was."""
    generation.status = "failed"
    generation.finished_at = datetime.now(UTC)
    generation.failure_kind = kind
    generation.failure_reason = reason


def _id(version: DocumentVersion | None) -> int | None:
    return None if version is None else version.id


def edited_by_hand(
    application: Application, latest: CoverLetterDraft | None, text: str
) -> CoverLetterDraft:
    """A new draft the user wrote, editing `latest` or from nothing; the caller adds it.
    It keeps the unsupported requirements of the draft it edits, which are about the
    posting and the profile, not the wording, and that draft's posting content hash, since
    its text was written against the posting then; a draft from nothing takes the posting's
    now."""
    return CoverLetterDraft(
        owner_id=application.owner_id,
        application_id=application.id,
        origin="edited_by_hand",
        text=text,
        unsupported_requirements=[] if latest is None else latest.unsupported_requirements,
        content_hash=application.job_posting.content_hash
        if latest is None
        else latest.content_hash,
    )


def restored(draft: CoverLetterDraft) -> CoverLetterDraft:
    """A new draft copying `draft`, its text and its whole record, to make it the latest
    again; the caller adds it."""
    return CoverLetterDraft(
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
    )


async def lock_sent(
    session: AsyncSession, application: Application, change: ApplicationStateChange
) -> None:
    """On a move to Applied, lock the latest draft as the letter sent, or record that none
    was. Moving back to Preparing unlocks the Cover Letter, and the next move to Applied
    locks the latest draft then."""
    if change.state == "applied":
        change.sent_draft = await latest_draft(session, application)


def latest_move_to_applied(application: Application) -> ApplicationStateChange | None:
    """The Application's latest move to Applied, with the letter it sent; None before any.
    The letter stays the one sent even if its draft is deleted later."""
    return next((c for c in reversed(application.history) if c.state == "applied"), None)


def posting_edited_since(draft: CoverLetterDraft | None, application: Application) -> bool | None:
    """Whether the posting's text changed since `draft` was made; None with no draft."""
    if draft is None:
        return None
    return draft.content_hash != application.job_posting.content_hash


def delete_draft(draft: CoverLetterDraft) -> None:
    """Mark the draft deleted, keeping it: hidden from the letter and its drafts, and
    left out of the quality aids. The draft before it is the letter again."""
    draft.deleted_at = datetime.now(UTC)


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


async def draft(
    session: AsyncSession, application: Application, draft_id: int
) -> CoverLetterDraft | None:
    """One of the Application's live drafts; a deleted one is hidden."""
    return await session.scalar(_live_drafts(application).where(CoverLetterDraft.id == draft_id))


async def drafts(session: AsyncSession, application: Application) -> list[CoverLetterDraft]:
    """The Application's live drafts, the latest first."""
    return list(await session.scalars(_live_drafts(application)))


async def latest_draft(session: AsyncSession, application: Application) -> CoverLetterDraft | None:
    """The Application's Cover Letter: its latest live draft, if it has one."""
    return await session.scalar(_live_drafts(application).limit(1))


async def latest_generation(
    session: AsyncSession, application: Application
) -> CoverLetterGeneration | None:
    """The Application's latest request to generate a draft, whatever became of it."""
    return await session.scalar(
        select(CoverLetterGeneration)
        .where(CoverLetterGeneration.application_id == application.id)
        .order_by(CoverLetterGeneration.id.desc())
        .limit(1)
    )
