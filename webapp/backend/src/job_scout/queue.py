"""The background task queue: Procrastinate on the webapp's Postgres.

Request handlers only enqueue tasks and report their status; the worker runs
them. Each process builds its own task queue from its settings. The task bodies
live in the package whose job they run (`<package>/tasks.py`).
"""

from collections.abc import Awaitable, Callable, Mapping

import procrastinate
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from job_scout.config import Settings
from job_scout.llm.interface import Llm

EXTRACT_CLIPPING = "extract_clipping"
EVALUATE = "evaluate"
GENERATE_COVER_LETTER = "generate_cover_letter"

# A task calling the LLM runs at most this many times before it records the failure
LLM_ATTEMPTS = 3

# A task body: it gets the job's context and the arguments it was enqueued with
type Task = Callable[..., Awaitable[None]]


class LlmCallFailed(Exception):
    """Raised by a task to have the queue retry its failed LLM call."""


def build(settings: Settings, llm_tasks: Mapping[str, Task] | None = None) -> procrastinate.App:
    """The task queue, running `llm_tasks` (each body by its task name) with retries."""
    task_queue = procrastinate.App(
        connector=procrastinate.PsycopgConnector(conninfo=settings.database_url)
    )
    llm_retry = procrastinate.RetryStrategy(
        max_attempts=LLM_ATTEMPTS - 1,  # retries after the first run
        wait=settings.llm_retry_wait_seconds,
    )
    for name, body in (llm_tasks or {}).items():
        task_queue.task(name=name, pass_context=True, retry=llm_retry)(body)
    return task_queue


def worker_context(sessions: async_sessionmaker[AsyncSession], llm: Llm) -> dict[str, object]:
    """What the worker hands every task, as `JobContext.additional_context`."""
    return {"sessions": sessions, "llm": llm}


async def enqueue_extract_clipping(task_queue: procrastinate.App, clipping_id: int) -> None:
    await task_queue.configure_task(EXTRACT_CLIPPING).defer_async(clipping_id=clipping_id)


async def enqueue_evaluate(task_queue: procrastinate.App, evaluation_id: int) -> None:
    await task_queue.configure_task(EVALUATE).defer_async(evaluation_id=evaluation_id)


async def enqueue_generate_cover_letter(task_queue: procrastinate.App, generation_id: int) -> None:
    await task_queue.configure_task(GENERATE_COVER_LETTER).defer_async(generation_id=generation_id)


def is_last_attempt(context: procrastinate.JobContext) -> bool:
    return context.job.attempts >= LLM_ATTEMPTS - 1  # attempts counts earlier runs
