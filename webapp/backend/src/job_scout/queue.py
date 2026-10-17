"""The background task queue: Procrastinate on the webapp's Postgres.

Request handlers only enqueue tasks and report their status; the worker runs
them. Each process builds its own task queue from its settings.
"""

import procrastinate
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from job_scout import clippings, evaluations
from job_scout.config import Settings
from job_scout.llm import Failure, Llm
from job_scout.models import Clipping, Evaluation

EXTRACT_CLIPPING = "extract_clipping"
EVALUATE = "evaluate"

# A task calling the LLM runs at most this many times before it records the failure
LLM_ATTEMPTS = 3


class LlmCallFailed(Exception):
    """Raised by a task to have the queue retry its failed LLM call."""


def build(settings: Settings) -> procrastinate.App:
    task_queue = procrastinate.App(
        connector=procrastinate.PsycopgConnector(conninfo=settings.database_url)
    )
    llm_retry = procrastinate.RetryStrategy(
        max_attempts=LLM_ATTEMPTS - 1,  # retries after the first run
        wait=settings.llm_retry_wait_seconds,
    )
    task_queue.task(name=EXTRACT_CLIPPING, pass_context=True, retry=llm_retry)(extract_clipping)
    task_queue.task(name=EVALUATE, pass_context=True, retry=llm_retry)(evaluate)
    return task_queue


def worker_context(sessions: async_sessionmaker[AsyncSession], llm: Llm) -> dict[str, object]:
    """What the worker hands every task, as `JobContext.additional_context`."""
    return {"sessions": sessions, "llm": llm}


async def enqueue_extract_clipping(task_queue: procrastinate.App, clipping_id: int) -> None:
    await task_queue.configure_task(EXTRACT_CLIPPING).defer_async(clipping_id=clipping_id)


async def extract_clipping(context: procrastinate.JobContext, clipping_id: int) -> None:
    """Read a pending Clipping's pasted text with the LLM and store the outcome.

    A failed call, or any other error, is retried on the queue; only the last
    attempt's failure is stored.
    """
    sessions: async_sessionmaker[AsyncSession] = context.additional_context["sessions"]
    llm: Llm = context.additional_context["llm"]
    async with sessions() as session:
        clipping = await session.get_one(Clipping, clipping_id)
    if clipping.status != "pending":
        return
    # No transaction is held open while the LLM call runs
    try:
        outcome = await llm.extract_manual_entry(clipping.pasted_text)
    except Exception as error:
        # Not an LLM failure (a bug, say), but it must not leave the clipping pending for good
        if not _is_last_attempt(context):
            raise
        async with sessions.begin() as session:
            clipping = await session.get_one(Clipping, clipping_id)
            clippings.record_failure(clipping, Failure("error", f"Unexpected error: {error!r}"))
        return
    if isinstance(outcome.result, Failure) and not _is_last_attempt(context):
        raise LlmCallFailed(outcome.result.reason)
    async with sessions.begin() as session:
        clipping = await session.get_one(Clipping, clipping_id)
        clippings.record(clipping, outcome)


async def enqueue_evaluate(task_queue: procrastinate.App, evaluation_id: int) -> None:
    await task_queue.configure_task(EVALUATE).defer_async(evaluation_id=evaluation_id)


async def evaluate(context: procrastinate.JobContext, evaluation_id: int) -> None:
    """Run a queued Evaluation: call the LLM, check its answer, store the outcome.

    A failed call or a failed check, or any other error, is retried on the
    queue; only the last attempt's failure is stored. Each attempt reads the
    user inputs and posting afresh.
    """
    sessions: async_sessionmaker[AsyncSession] = context.additional_context["sessions"]
    llm: Llm = context.additional_context["llm"]
    async with sessions.begin() as session:
        run = await session.get_one(Evaluation, evaluation_id)
        if run.status not in ("queued", "running"):
            return
        inputs = await evaluations.start(session, run)
        missing = inputs.missing()
        if missing is not None:
            # Retrying would not help: the user has to write the input first
            evaluations.record_missing_input(run, inputs, missing)
            return
    # No transaction is held open while the LLM call runs
    try:
        checked = evaluations.check(await llm.evaluate(inputs.prompt()), inputs)
    except Exception as error:
        # Not an LLM failure (a bug, say), but it must not leave the Evaluation running for good
        if not _is_last_attempt(context):
            raise
        async with sessions.begin() as session:
            run = await session.get_one(Evaluation, evaluation_id)
            evaluations.record_failure(run, Failure("error", f"Unexpected error: {error!r}"))
        return
    if isinstance(checked.result, Failure) and not _is_last_attempt(context):
        raise LlmCallFailed(checked.result.reason)
    async with sessions.begin() as session:
        run = await session.get_one(Evaluation, evaluation_id)
        evaluations.record(run, inputs, checked)


def _is_last_attempt(context: procrastinate.JobContext) -> bool:
    return context.job.attempts >= LLM_ATTEMPTS - 1  # attempts counts earlier runs
