"""The background task queue: Procrastinate on the webapp's Postgres.

Request handlers only enqueue tasks and report their status; the worker runs
them. Each process builds its own task queue from its settings.
"""

from datetime import UTC, datetime

import procrastinate
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from job_scout.config import Settings
from job_scout.models import JobPosting

MARK_PROCESSED = "mark_processed"


def build(settings: Settings) -> procrastinate.App:
    task_queue = procrastinate.App(
        connector=procrastinate.PsycopgConnector(conninfo=settings.database_url)
    )
    task_queue.task(name=MARK_PROCESSED, pass_context=True)(mark_processed)
    return task_queue


def worker_context(sessions: async_sessionmaker[AsyncSession]) -> dict[str, object]:
    """What the worker hands every task, as `JobContext.additional_context`."""
    return {"sessions": sessions}


async def enqueue_mark_processed(task_queue: procrastinate.App, posting_id: int) -> None:
    await task_queue.configure_task(MARK_PROCESSED).defer_async(posting_id=posting_id)


async def mark_processed(context: procrastinate.JobContext, posting_id: int) -> None:
    """Walking skeleton task: stamps the posting, proving the queue end to end."""
    sessions: async_sessionmaker[AsyncSession] = context.additional_context["sessions"]
    async with sessions.begin() as session:
        posting = await session.get_one(JobPosting, posting_id)
        posting.processed_at = datetime.now(UTC)
