"""When a Job Posting is evaluated again: the user's "re-run all" and a change to the
posting's text.

Only a posting the user has not acted on is evaluated again by itself. Acting on it, with
any Triage or a live Application, means the user judged it by the Evaluation they saw, so
that one stays, shown as outdated, until they ask for another.
"""

import uuid

import procrastinate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_scout.applications import domain as applications
from job_scout.evaluations import domain as evaluations
from job_scout.evaluations.models import Evaluation
from job_scout.evaluations.tasks import EVALUATION
from job_scout.job_postings import domain as job_postings
from job_scout.job_postings.models import JobPosting
from job_scout.llm_runs import domain as llm_runs
from job_scout.triage import domain as triage


async def acted_on(session: AsyncSession, posting: JobPosting) -> bool:
    """Whether the user has acted on the posting: it has a Triage or a live Application."""
    return posting.id in await _acted_on_ids(session, posting.owner_id, [posting.id])


async def rerun_all_unacted(
    session: AsyncSession, task_queue: procrastinate.App, *, owner_id: uuid.UUID
) -> list[Evaluation]:
    """Queue a new Evaluation, with the current user inputs, of every open posting the user
    has not acted on, committed. A posting with an Evaluation under way, unless stuck, is
    left to it. Closed and acted-on postings are skipped."""
    open_postings = await session.scalars(
        select(JobPosting)
        .where(JobPosting.owner_id == owner_id, JobPosting.closed_at.is_(None))
        .order_by(JobPosting.id)  # one order, so two requests locking postings cannot deadlock
    )
    candidates = [*open_postings]
    skipped = await _acted_on_ids(session, owner_id, [posting.id for posting in candidates])
    runs = []
    for posting in candidates:
        if posting.id in skipped:
            continue
        # Locked, then judged again: the user may have acted or closed it meanwhile
        await job_postings.lock(session, posting)
        if posting.closed_at is not None or await acted_on(session, posting):
            continue
        run = await _rerun_unless_under_way(session, posting)
        if run is not None:
            runs.append(run)
    await llm_runs.commit_and_enqueue(session, task_queue, EVALUATION, *runs)
    return runs


async def update_text(
    session: AsyncSession,
    task_queue: procrastinate.App,
    posting: JobPosting,
    *,
    title: str,
    location_text: str | None,
    description: str,
) -> Evaluation | None:
    """The one path that changes a posting's text, committed; Pipelines will use it.

    A change to the text (the content hash) queues a new Evaluation, returned, if the
    posting is not acted on. If it is, the old Evaluation stays and is outdated. Text that
    comes out the same changes nothing, and neither does any change to the posting's
    dates or metadata, which this path does not touch.
    """
    await job_postings.lock(session, posting)
    before = posting.content_hash
    job_postings.set_text(
        posting, title=title, location_text=location_text, description=description
    )
    run = None
    if posting.content_hash != before and not await acted_on(session, posting):
        run = await _rerun_unless_under_way(session, posting)
    await llm_runs.commit_and_enqueue(
        session, task_queue, EVALUATION, *([] if run is None else [run])
    )
    return run


async def _rerun_unless_under_way(session: AsyncSession, posting: JobPosting) -> Evaluation | None:
    """A new queued Evaluation, added to the session, unless one is under way: it is left
    to finish, and read the posting as it was when it started."""
    try:
        return await evaluations.rerun(session, posting)
    except llm_runs.RunUnderWay:
        return None


async def _acted_on_ids(
    session: AsyncSession, owner_id: uuid.UUID, job_posting_ids: list[int]
) -> set[int]:
    triaged = await triage.triages_by_posting(
        session, owner_id=owner_id, job_posting_ids=job_posting_ids
    )
    applying = await applications.live_by_posting(
        session, owner_id=owner_id, job_posting_ids=job_posting_ids
    )
    return {*triaged, *applying}
