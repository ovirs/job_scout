"""Notes: free-text, dated, on a Job Posting or on an Application.

A posting's notes stay on the posting, and an Application shows them alongside its own.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from job_scout.models import Application, JobPosting, Note


def on_posting(posting: JobPosting, text: str) -> Note:
    """A new note on the posting; the caller adds it."""
    return Note(owner_id=posting.owner_id, job_posting_id=posting.id, text=text)


def on_application(application: Application, text: str) -> Note:
    """A new note on the Application; the caller adds it."""
    return Note(owner_id=application.owner_id, application_id=application.id, text=text)


async def note(session: AsyncSession, *, owner_id: uuid.UUID, note_id: int) -> Note | None:
    """A live note; one that is deleted, or on a deleted Application, is hidden as if it
    never existed."""
    return await session.scalar(
        select(Note)
        .outerjoin(Application, Note.application_id == Application.id)
        .where(
            Note.id == note_id,
            Note.owner_id == owner_id,
            Note.deleted_at.is_(None),
            Application.deleted_at.is_(None),
        )
    )


def delete(note: Note) -> None:
    """Mark the note deleted, keeping it."""
    note.deleted_at = datetime.now(UTC)


async def of_posting(session: AsyncSession, posting: JobPosting) -> list[Note]:
    """The posting's live notes, the first first."""
    return await _live(session, posting.owner_id, Note.job_posting_id == posting.id)


async def of_application(session: AsyncSession, application: Application) -> list[Note]:
    """The Application's live notes and its posting's, together, the first first."""
    return await _live(
        session,
        application.owner_id,
        or_(
            Note.application_id == application.id,
            Note.job_posting_id == application.job_posting_id,
        ),
    )


async def _live(session: AsyncSession, owner_id: uuid.UUID, on: ColumnElement[bool]) -> list[Note]:
    found = await session.scalars(
        select(Note)
        .where(Note.owner_id == owner_id, on, Note.deleted_at.is_(None))
        .order_by(Note.created_at, Note.id)
    )
    return list(found)
