"""The background task that reads a Clipping with the LLM: an LLM run (see `llm_runs`).

The LLM names the description's first and last line; code cuts the description from
the pasted text, so the stored description is always the user's own text.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from job_scout.clippings.extraction import ManualEntryExtraction
from job_scout.clippings.models import Clipping
from job_scout.llm.interface import Llm, Outcome, Step
from job_scout.llm_runs.domain import Refusal


class ClippingExtraction:
    """Reads a Clipping's pasted text and stores the extraction on it."""

    task_name = "extract_clipping"
    run_type = Clipping
    step: Step = "extraction"

    async def gather(self, session: AsyncSession, run: Clipping) -> str | Refusal:
        return run.pasted_text

    async def call(self, llm: Llm, inputs: str) -> Outcome[ManualEntryExtraction]:
        return await llm.extract_manual_entry(inputs)

    async def record(
        self, session: AsyncSession, run: Clipping, inputs: str, result: ManualEntryExtraction
    ) -> Refusal | None:
        record(run, result)
        return None


EXTRACTION = ClippingExtraction()


def record(clipping: Clipping, result: ManualEntryExtraction) -> None:
    """Store an extraction, with the description cut from the pasted text."""
    description = cut_description(
        clipping.pasted_text, result.description_first_line, result.description_last_line
    )
    clipping.extraction = result.model_dump(mode="json")
    clipping.description = clipping.pasted_text if description is None else description
    clipping.description_cut = description is not None


def cut_description(pasted_text: str, first_line: str | None, last_line: str | None) -> str | None:
    """The whole lines of the pasted text from the first occurrence of `first_line` to
    the next occurrence of `last_line` after it, or within it for a one-line
    description; None when either is not found."""
    first = (first_line or "").strip()
    last = (last_line or "").strip()
    if not first or not last:
        return None
    first_at = pasted_text.find(first)
    if first_at < 0:
        return None
    last_at = pasted_text.find(last, first_at + len(first))
    if last_at < 0:
        last_at = pasted_text.find(last, first_at)
    if last_at < 0:
        return None
    start = pasted_text.rfind("\n", 0, first_at) + 1
    end = pasted_text.find("\n", last_at + len(last))
    return pasted_text[start : len(pasted_text) if end < 0 else end]
