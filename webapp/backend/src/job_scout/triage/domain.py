"""Triage: the user's own call on a Job Posting (Interested, Maybe, Ignored); untriaged is
the absence of one. The lists that follow from it are `posting_view`'s.

The user sets it through the Applications package, which keeps it locked at Interested
while the posting has a live Application; the Triage package knows nothing of that."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_scout.job_postings import domain as job_postings
from job_scout.job_postings.models import JobPosting
from job_scout.triage.models import Triage, TriageValue


async def set_triage(session: AsyncSession, posting: JobPosting, value: TriageValue) -> Triage:
    """The user's Triage of the posting: the first creates it, later ones change its value.
    Any posting can be triaged, whatever its Evaluation.

    The posting is locked first, so two first Triages do not both create one: the later
    waits, then changes the value the earlier set.
    """
    await job_postings.lock(session, posting)
    triage = await session.scalar(select(Triage).where(Triage.job_posting_id == posting.id))
    now = datetime.now(UTC)
    if triage is None:
        triage = Triage(
            owner_id=posting.owner_id,
            job_posting_id=posting.id,
            value=value,
            origin="user",
            created_at=now,
            changed_at=now,
        )
        session.add(triage)
    else:
        triage.value = value
        triage.origin = "user"
        triage.changed_at = now
    return triage


async def triages_by_posting(
    session: AsyncSession, *, owner_id: uuid.UUID, job_posting_ids: list[int]
) -> dict[int, Triage]:
    triages = await session.scalars(
        select(Triage).where(
            Triage.owner_id == owner_id, Triage.job_posting_id.in_(job_posting_ids)
        )
    )
    return {triage.job_posting_id: triage for triage in triages}
