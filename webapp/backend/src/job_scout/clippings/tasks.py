"""The background task that reads a Clipping with the LLM: an LLM run (see `llm_runs`)."""

from sqlalchemy.ext.asyncio import AsyncSession

from job_scout.clippings import domain as clippings
from job_scout.clippings.extraction import ManualEntryExtraction
from job_scout.clippings.models import Clipping
from job_scout.llm.interface import Llm, Outcome
from job_scout.llm_runs.domain import Refusal


class ClippingExtraction:
    """Reads a Clipping's pasted text and stores the extraction on it."""

    task_name = "extract_clipping"
    run_type = Clipping

    async def gather(self, session: AsyncSession, run: Clipping) -> str | Refusal:
        return run.pasted_text

    async def call(self, llm: Llm, inputs: str) -> Outcome[ManualEntryExtraction]:
        return await llm.extract_manual_entry(inputs)

    async def record(
        self, session: AsyncSession, run: Clipping, inputs: str, result: ManualEntryExtraction
    ) -> Refusal | None:
        clippings.record(run, result)
        return None


EXTRACTION = ClippingExtraction()
