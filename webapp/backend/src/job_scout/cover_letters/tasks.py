"""The background job that writes a Cover Letter draft with the LLM."""

import procrastinate
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from job_scout.applications.models import Application
from job_scout.cover_letters import domain as cover_letters
from job_scout.cover_letters.models import CoverLetterGeneration
from job_scout.llm.interface import Failure, Llm
from job_scout.queue import LlmCallFailed, is_last_attempt


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
        if not is_last_attempt(context):
            raise
        async with sessions.begin() as session:
            generation = await session.get_one(CoverLetterGeneration, generation_id)
            cover_letters.record_failure(generation, "error", f"Unexpected error: {error!r}")
        return
    if isinstance(checked.result, Failure) and not is_last_attempt(context):
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
