"""Applications: the user's tracked progress in applying for a Job Posting.

An Application starts in Preparing and is moved by hand between any two states. A
posting has at most one live (not deleted) Application, and while it has one its Triage
is Interested and locked.
"""

import uuid
from datetime import UTC, datetime
from typing import get_args

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_scout.models import Application, ApplicationState, ApplicationStateChange, JobPosting

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


def start(posting: JobPosting) -> Application:
    """A new Application in Preparing; the caller adds it, once it has checked that the
    posting has no live Application, and sets the posting's Triage to Interested."""
    now = datetime.now(UTC)
    return Application(
        owner_id=posting.owner_id,
        job_posting=posting,
        state="preparing",
        created_at=now,
        history=[ApplicationStateChange(state="preparing", changed_at=now)],
    )


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
    session: AsyncSession, *, owner_id: uuid.UUID, application_id: int
) -> Application | None:
    """A live Application; a deleted one is hidden as if it never existed."""
    return await session.scalar(
        select(Application).where(
            Application.id == application_id,
            Application.owner_id == owner_id,
            Application.deleted_at.is_(None),
        )
    )


def set_state(application: Application, state: ApplicationState) -> None:
    """Move the Application to any state, recording the move in its history; moving to
    the state it is in records nothing. The first move to Applied copies the posting."""
    if state == application.state:
        return
    now = datetime.now(UTC)
    application.state = state
    application.history.append(ApplicationStateChange(state=state, changed_at=now))
    if state == "applied" and application.copied_at is None:
        _copy_posting(application, now)


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


def delete(application: Application) -> None:
    """Mark the Application deleted, keeping it; allowed only while Preparing (the caller
    checks). An Application past Preparing is closed instead."""
    application.deleted_at = datetime.now(UTC)


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
