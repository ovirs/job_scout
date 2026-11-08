"""Applications: the user's tracked progress in applying for a Job Posting.

An Application starts in Preparing and is moved by hand between any two states. A
posting has at most one live (not deleted) Application, and while it has one its Triage
is Interested and locked.

Each operation enforces these rules and refuses with a `Refused` error otherwise; an
unknown posting or Application raises `NoSuchJobPosting` or `NoSuchApplication`.

The package also holds the acted-on rule, which needs both the Triage and the
Application: a posting with any Triage or a live Application is acted on, and its
Evaluation is no longer re-run, by a re-run of every unacted posting or by a change to
the posting's text, which leaves it outdated instead.
"""

import uuid
from datetime import UTC, datetime
from typing import get_args

import procrastinate
from sqlalchemy import Exists, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from job_scout.applications.models import Application, ApplicationState, ApplicationStateChange
from job_scout.evaluations import domain as evaluations
from job_scout.evaluations.models import Evaluation
from job_scout.evaluations.tasks import EVALUATION
from job_scout.job_postings import domain as job_postings
from job_scout.job_postings.models import JobPosting
from job_scout.llm_runs import domain as llm_runs
from job_scout.triage import domain as triage
from job_scout.triage.models import Triage, TriageValue

# The usual progression, Preparing to No response; lists follow it
STATES: tuple[ApplicationState, ...] = get_args(ApplicationState)
CLOSED_STATES: frozenset[ApplicationState] = frozenset(
    ["accepted", "rejected", "withdrawn", "no_response"]
)


def is_closed(application: Application) -> bool:
    return application.state in CLOSED_STATES


def state_changed_at(application: Application) -> datetime:
    """When the Application moved to its current state."""
    return application.history[-1].changed_at


class NoSuchJobPosting(Exception):
    """The owner has no Job Posting with this id."""


class NoSuchApplication(Exception):
    """The owner has no live Application with this id."""


class Refused(Exception):
    """The Application rules refuse the operation; the message says why."""


class AlreadyApplying(Refused):
    """The posting already has a live Application."""


class NotDeletable(Refused):
    """Only an Application in Preparing is deleted; past it, one is closed instead."""


class TriageLocked(Refused):
    """The posting's Triage stays Interested while it has a live Application."""


async def start(
    session: AsyncSession,
    task_queue: procrastinate.App,
    *,
    owner_id: uuid.UUID,
    job_posting_id: int,
) -> Application:
    """Start applying: a new Application in Preparing, with the posting's Triage set to
    Interested, committed. Refused while the posting has a live Application. Queues an
    Evaluation of a posting that has none done or under way."""
    posting = await _posting(session, owner_id, job_posting_id)
    if await live(session, posting) is not None:
        raise AlreadyApplying("The posting already has a live Application")
    await triage.set_triage(session, posting, "interested")
    now = datetime.now(UTC)
    application = Application(
        owner_id=posting.owner_id,
        job_posting=posting,
        state="preparing",
        created_at=now,
        history=[ApplicationStateChange(state="preparing", changed_at=now)],
    )
    session.add(application)
    run = await evaluations.queued_unless_evaluated(session, posting)
    await llm_runs.commit_and_enqueue(
        session, task_queue, EVALUATION, *([] if run is None else [run])
    )
    return application


async def set_triage(
    session: AsyncSession, *, owner_id: uuid.UUID, job_posting_id: int, value: TriageValue
) -> JobPosting:
    """The user's Triage of the posting, replacing any earlier one, committed; allowed for
    any posting, evaluated or not. Refused while the posting has a live Application,
    which keeps it locked at Interested."""
    posting = await _posting(session, owner_id, job_posting_id)
    if await live(session, posting) is not None:
        raise TriageLocked(
            "The Triage is locked at Interested while the posting has a live Application"
        )
    await triage.set_triage(session, posting, value)
    await session.commit()
    return posting


async def _posting(session: AsyncSession, owner_id: uuid.UUID, job_posting_id: int) -> JobPosting:
    """The posting, locked until the transaction ends, so its Application and Triage are
    checked and changed by one operation at a time."""
    found = await job_postings.job_posting(
        session, owner_id=owner_id, job_posting_id=job_posting_id
    )
    if found is None:
        raise NoSuchJobPosting
    await job_postings.lock(session, found)
    return found


async def live(session: AsyncSession, posting: JobPosting) -> Application | None:
    """The posting's live Application, if it has one."""
    found = await live_by_posting(session, owner_id=posting.owner_id, job_posting_ids=[posting.id])
    return found.get(posting.id)


async def live_by_posting(
    session: AsyncSession, *, owner_id: uuid.UUID, job_posting_ids: list[int]
) -> dict[int, Application]:
    """The live Application of each of the postings that has one."""
    found = await session.scalars(
        select(Application).where(
            Application.owner_id == owner_id,
            Application.job_posting_id.in_(job_posting_ids),
            Application.deleted_at.is_(None),
        )
    )
    return {application.job_posting_id: application for application in found}


async def application(
    session: AsyncSession, *, owner_id: uuid.UUID, application_id: int, for_update: bool = False
) -> Application | None:
    """A live Application; a deleted one is hidden as if it never existed. `for_update`
    locks it until the transaction ends, so two requests cannot both change it, and
    reloads it, so what was committed while waiting for the lock is what it holds."""
    query = select(Application).where(
        Application.id == application_id,
        Application.owner_id == owner_id,
        Application.deleted_at.is_(None),
    )
    if for_update:
        query = query.with_for_update().execution_options(populate_existing=True)
    return await session.scalar(query)


async def move(
    session: AsyncSession, *, owner_id: uuid.UUID, application_id: int, state: ApplicationState
) -> Application:
    """Move the Application to any state, from any other, committed; each move is kept,
    dated, in its history, and moving to the state it is in records nothing. The first
    move to Applied copies the posting.

    The Application is locked before the move is timed: a Cover Letter draft is stored
    while holding the same lock, so one stored just before the move is always made
    before it, and counts as sent."""
    application = await _locked_application(session, owner_id, application_id)
    if state != application.state:
        now = datetime.now(UTC)
        application.state = state
        application.history.append(ApplicationStateChange(state=state, changed_at=now))
        if state == "applied" and application.copied_at is None:
            _copy_posting(application, now)
    await session.commit()
    return application


async def _locked_application(
    session: AsyncSession, owner_id: uuid.UUID, application_id: int
) -> Application:
    """The live Application, locked until the transaction ends, so two operations cannot
    both change it."""
    found = await application(
        session, owner_id=owner_id, application_id=application_id, for_update=True
    )
    if found is None:
        raise NoSuchApplication
    return found


def _copy_posting(application: Application, now: datetime) -> None:
    posting = application.job_posting
    application.copied_at = now
    application.copy_title = posting.title
    application.copy_company = posting.company
    application.copy_location_text = posting.location_text
    application.copy_description = posting.description
    application.copy_url = posting.url
    application.copy_content_hash = posting.content_hash


def posting_changed_since_copy(application: Application) -> bool | None:
    """Whether the posting's text changed since the Application copied it; None before
    the copy is taken."""
    if application.copy_content_hash is None:
        return None
    return application.copy_content_hash != application.job_posting.content_hash


async def delete(session: AsyncSession, *, owner_id: uuid.UUID, application_id: int) -> None:
    """Delete the Application, keeping it, committed: it is hidden everywhere, and the
    posting's Triage stays Interested, changeable again. Refused unless the Application
    is Preparing; past it, an Application is closed rather than deleted. Locked first, so
    it cannot move past Preparing while it is deleted."""
    found = await _locked_application(session, owner_id, application_id)
    if found.state != "preparing":
        raise NotDeletable("Only an Application in Preparing can be deleted")
    found.deleted_at = datetime.now(UTC)
    await session.commit()


async def by_state(
    session: AsyncSession, *, owner_id: uuid.UUID, closed: bool | None = None
) -> list[Application]:
    """The live Applications, in the order of their states, Preparing to No response,
    the latest move first within a state; with `closed`, only the closed ones or only
    those in flight."""
    found = await session.scalars(
        select(Application).where(
            Application.owner_id == owner_id, Application.deleted_at.is_(None)
        )
    )
    members = [a for a in found if closed is None or is_closed(a) == closed]
    members.sort(key=state_changed_at, reverse=True)
    members.sort(key=lambda a: STATES.index(a.state))
    return members


async def rerun_unacted(
    session: AsyncSession, task_queue: procrastinate.App, *, owner_id: uuid.UUID
) -> list[Evaluation]:
    """Queue a new Evaluation, with the current user inputs, of every open posting the
    user has not acted on, committed; returns them. A posting whose Evaluation is under
    way is left to it."""
    postings = await session.scalars(
        select(JobPosting)
        .where(JobPosting.owner_id == owner_id, JobPosting.closed_at.is_(None))
        .where(~_has_triage(), ~_has_live_application())
        .order_by(JobPosting.id)
    )
    runs = []
    for posting in postings:
        await job_postings.lock(session, posting)
        # Triaged, applied for or closed since it was found
        if posting.closed_at is not None or await acted_on(session, posting):
            continue
        run = await evaluations.rerun_unless_under_way(session, posting)
        if run is not None:
            runs.append(run)
    await llm_runs.commit_and_enqueue(session, task_queue, EVALUATION, *runs)
    return runs


async def acted_on(session: AsyncSession, posting: JobPosting) -> bool:
    """Whether the user has acted on the posting: it has a Triage or a live Application."""
    found = await session.scalar(
        select(JobPosting.id).where(
            JobPosting.id == posting.id, _has_triage() | _has_live_application()
        )
    )
    return found is not None


async def update_text(
    session: AsyncSession,
    task_queue: procrastinate.App,
    posting: JobPosting,
    *,
    title: str,
    location_text: str | None,
    description: str,
) -> Evaluation | None:
    """The update path for a stored posting's text, committed. The content hash is
    recomputed, and when it changes, a posting the user has not acted on gets a new
    Evaluation, returned, unless one is under way (a queued one reads the new text when it
    starts; a running one has read the old text, so its result shows outdated until the
    posting is re-run by hand or by a re-run of every unacted one); an acted-on posting keeps its
    Evaluation, which is now outdated. Pipelines will use it; phase 1 offers the user no
    action for it. Other changes the caller made to the posting (its dates, its metadata)
    are committed with it, and trigger nothing."""
    await session.flush()  # so the lock, which reloads the posting, keeps those changes
    await job_postings.lock(session, posting)
    before = posting.content_hash
    job_postings.set_text(
        posting, title=title, location_text=location_text, description=description
    )
    runs = []
    if posting.content_hash != before and not await acted_on(session, posting):
        run = await evaluations.rerun_unless_under_way(session, posting)
        runs = [] if run is None else [run]
    await llm_runs.commit_and_enqueue(session, task_queue, EVALUATION, *runs)
    return runs[0] if runs else None


def _has_triage() -> Exists:
    return exists().where(Triage.job_posting_id == JobPosting.id)


def _has_live_application() -> Exists:
    return exists().where(
        Application.job_posting_id == JobPosting.id, Application.deleted_at.is_(None)
    )
