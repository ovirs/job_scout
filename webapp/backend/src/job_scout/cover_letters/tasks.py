"""The background task that writes a Cover Letter draft with the LLM: an LLM run (see
`llm_runs`).

Each attempt reads the user inputs and posting afresh. No failure touches the Cover
Letter. An Application that left Preparing, or was deleted, before the draft is stored
gets no draft: the run is refused as locked.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from job_scout.applications.models import Application
from job_scout.cover_letters import generation
from job_scout.cover_letters.generation import Inputs
from job_scout.cover_letters.models import CoverLetterGeneration
from job_scout.cover_letters.prompt import CoverLetterResult
from job_scout.llm.interface import Llm, Outcome
from job_scout.llm_runs.domain import Refusal


class CoverLetterGenerationTask:
    """Writes a draft from the posting and the user's inputs, and adds it to the letter."""

    task_name = "generate_cover_letter"
    run_type = CoverLetterGeneration

    async def gather(self, session: AsyncSession, run: CoverLetterGeneration) -> Inputs | Refusal:
        locked = await _locked(session, run)
        if locked is not None:
            return locked
        inputs = await generation.gather(session, run)
        missing = inputs.missing()
        # Retrying would not help: the user has to write the input first
        return inputs if missing is None else Refusal("missing_input", missing)

    async def call(self, llm: Llm, inputs: Inputs) -> Outcome[CoverLetterResult]:
        return generation.check(await llm.write_cover_letter(inputs.prompt()))

    async def record(
        self,
        session: AsyncSession,
        run: CoverLetterGeneration,
        inputs: Inputs,
        result: CoverLetterResult,
    ) -> Refusal | None:
        # The user may have moved on while the LLM wrote
        locked = await _locked(session, run)
        if locked is not None:
            return locked
        generation.record(session, run, inputs, result)
        return None


async def _locked(session: AsyncSession, run: CoverLetterGeneration) -> Refusal | None:
    """Why the run's Application takes no draft, if it does not. The Application stays
    locked until the transaction ends, so it cannot move to Applied before the draft is
    stored, and the draft is the letter sent."""
    application = await session.get_one(Application, run.application_id, with_for_update=True)
    reason = generation.locked_reason(application)
    return None if reason is None else Refusal("locked", reason)


GENERATION = CoverLetterGenerationTask()
