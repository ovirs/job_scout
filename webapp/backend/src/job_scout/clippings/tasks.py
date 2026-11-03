"""The background job that reads a Clipping with the LLM."""

import procrastinate
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from job_scout.clippings import domain as clippings
from job_scout.clippings.models import Clipping
from job_scout.llm.interface import Failure, Llm
from job_scout.queue import LlmCallFailed, is_last_attempt


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
        if not is_last_attempt(context):
            raise
        async with sessions.begin() as session:
            clipping = await session.get_one(Clipping, clipping_id)
            clippings.record_failure(clipping, Failure("error", f"Unexpected error: {error!r}"))
        return
    if isinstance(outcome.result, Failure) and not is_last_attempt(context):
        raise LlmCallFailed(outcome.result.reason)
    async with sessions.begin() as session:
        clipping = await session.get_one(Clipping, clipping_id)
        clippings.record(clipping, outcome)
