"""The background job that runs an Evaluation with the LLM."""

import procrastinate
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from job_scout.evaluations import domain as evaluations
from job_scout.evaluations.models import Evaluation
from job_scout.llm.interface import Failure, Llm
from job_scout.queue import LlmCallFailed, is_last_attempt


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
        if not is_last_attempt(context):
            raise
        async with sessions.begin() as session:
            run = await session.get_one(Evaluation, evaluation_id)
            evaluations.record_failure(run, Failure("error", f"Unexpected error: {error!r}"))
        return
    if isinstance(checked.result, Failure) and not is_last_attempt(context):
        raise LlmCallFailed(checked.result.reason)
    async with sessions.begin() as session:
        run = await session.get_one(Evaluation, evaluation_id)
        evaluations.record(run, inputs, checked)
