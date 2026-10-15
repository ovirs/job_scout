"""The resources every process (API server, worker) needs: database sessions and the task queue."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import procrastinate
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from job_scout import db, queue
from job_scout.config import Settings


@dataclass(frozen=True)
class Runtime:
    sessions: async_sessionmaker[AsyncSession]
    task_queue: procrastinate.App


@asynccontextmanager
async def open_runtime(settings: Settings) -> AsyncIterator[Runtime]:
    """Open the queue on a fresh engine; close both on exit."""
    engine = db.create_engine(settings)
    task_queue = queue.build(settings)
    try:
        async with task_queue.open_async():
            yield Runtime(db.create_sessionmaker(engine), task_queue)
    finally:
        await engine.dispose()
