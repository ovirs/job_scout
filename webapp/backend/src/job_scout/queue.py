"""The background task queue: Procrastinate on the webapp's Postgres.

Request handlers only enqueue tasks and report their status; the worker runs
them. Each process builds its own task queue from its settings. The LLM runs
register their tasks with `llm_runs.register`.
"""

import procrastinate
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from job_scout.config import Settings
from job_scout.llm.interface import Connect


def build(settings: Settings) -> procrastinate.App:
    """The task queue, with no tasks registered yet."""
    return procrastinate.App(
        connector=procrastinate.PsycopgConnector(conninfo=settings.database_url)
    )


def worker_context(
    sessions: async_sessionmaker[AsyncSession], connect: Connect
) -> dict[str, object]:
    """What the worker hands every task, as `JobContext.additional_context`: the database
    sessions, and how to connect to a Provider with a key."""
    return {"sessions": sessions, "connect": connect}
