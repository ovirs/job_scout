"""The background task queue: Procrastinate on the webapp's Postgres.

Request handlers only enqueue tasks and report their status; the worker runs
them. Each process builds its own task queue from its settings.
"""

import procrastinate
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from job_scout import clippings, cover_letters, evaluations
from job_scout.config import Settings
from job_scout.llm import Failure, Llm
from job_scout.models import Application, Clipping, CoverLetterGeneration, Evaluation

EXTRACT_CLIPPING = "extract_clipping"
EVALUATE = "evaluate"
GENERATE_COVER_LETTER = "generate_cover_letter"

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
    task_queue.task(name=GENERATE_COVER_LETTER, pass_context=True, retry=llm_retry)(
        generate_cover_letter
    )
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


async def enqueue_generate_cover_letter(task_queue: procrastinate.App, generation_id: int) -> None:
    await task_queue.configure_task(GENERATE_COVER_LETTER).defer_async(generation_id=generation_id)


async def generate_cover_letter(context: procrastinate.JobContext, generation_id: int) -> None:
    """Run a queued Cover Letter generation: call the LLM and store the draft it wrote.

    A failed call, or any other error, is retried on the queue; only the last attempt's
    failure is stored, and no failure touches the Cover Letter. Each attempt reads the
    user inputs and posting afresh. An Application that left Preparing, or was deleted,
    before the generation ran gets no draft.
    """
    sessions: async_sessionmaker[AsyncSession] = context.additional_context["sessions"]
    llm: Llm = context.additional_context["llm"]
    async with sessions.begin() as session:
        generation = await session.get_one(CoverLetterGeneration, generation_id)
        if generation.status not in ("queued", "running"):
            return
        locked = _locked_reason(await session.get_one(Application, generation.application_id))
        if locked is not None:
            cover_letters.record_failure(generation, "locked", locked)
            return
        inputs = await cover_letters.start(session, generation)
        missing = inputs.missing()
        if missing is not None:
            # Retrying would not help: the user has to write the input first
            cover_letters.record_failure(generation, "missing_input", missing)
            return
    # No transaction is held open while the LLM call runs
    try:
        checked = cover_letters.check(await llm.write_cover_letter(inputs.prompt()))
    except Exception as error:
        # Not an LLM failure (a bug, say), but it must not leave the generation running for good
        if not _is_last_attempt(context):
            raise
        async with sessions.begin() as session:
            generation = await session.get_one(CoverLetterGeneration, generation_id)
            cover_letters.record_failure(generation, "error", f"Unexpected error: {error!r}")
        return
    if isinstance(checked.result, Failure) and not _is_last_attempt(context):
        raise LlmCallFailed(checked.result.reason)
    async with sessions.begin() as session:
        generation = await session.get_one(CoverLetterGeneration, generation_id)
        # The user may have moved on while the LLM wrote
        locked = _locked_reason(await session.get_one(Application, generation.application_id))
        if locked is not None:
            cover_letters.record_failure(generation, "locked", locked)
            return
        cover_letters.record(session, generation, inputs, checked)


def _locked_reason(application: Application) -> str | None:
    """Why the Application's Cover Letter takes no new draft, if it does not."""
    if cover_letters.editable(application):
        return None
    if application.deleted_at is not None:
        return "The Application was deleted"
    return "The Application is no longer Preparing, so its Cover Letter is locked"


def _is_last_attempt(context: procrastinate.JobContext) -> bool:
    return context.job.attempts >= LLM_ATTEMPTS - 1  # attempts counts earlier runs
