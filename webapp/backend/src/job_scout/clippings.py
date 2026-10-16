"""Clippings: pasted text of a Job Posting, read by the LLM before the user confirms it.

The LLM names the description's first and last line; code cuts the description
from the pasted text, so the stored description is always the user's own text.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_scout.extraction import ManualEntryExtraction
from job_scout.llm import Failure, Outcome
from job_scout.models import Clipping


def submit(*, owner_id: uuid.UUID, pasted_text: str, url: str | None) -> Clipping:
    """A new pending clipping; the caller enqueues its extraction."""
    return Clipping(owner_id=owner_id, pasted_text=pasted_text, url=url, status="pending")


async def clipping(
    session: AsyncSession, *, owner_id: uuid.UUID, clipping_id: int
) -> Clipping | None:
    return await session.scalar(
        select(Clipping).where(Clipping.id == clipping_id, Clipping.owner_id == owner_id)
    )


def retry(clipping: Clipping) -> None:
    """Make a failed clipping pending again; the caller enqueues its extraction."""
    assert clipping.status == "failed"
    clipping.status = "pending"
    clipping.failure_kind = clipping.failure_reason = None


def record(clipping: Clipping, outcome: Outcome[ManualEntryExtraction]) -> None:
    """Store an extraction call's outcome: done with the cut description, or failed."""
    clipping.model = outcome.model
    clipping.prompt_version = outcome.prompt_version
    result = outcome.result
    if isinstance(result, Failure):
        _fail(clipping, result)
        return
    description = cut_description(
        clipping.pasted_text, result.description_first_line, result.description_last_line
    )
    clipping.status = "done"
    clipping.failure_kind = clipping.failure_reason = None
    clipping.extraction = result.model_dump(mode="json")
    clipping.description = clipping.pasted_text if description is None else description
    clipping.description_cut = description is not None


def record_failure(clipping: Clipping, failure: Failure) -> None:
    """Store an error outside the LLM call, which used no model or prompt."""
    clipping.model = clipping.prompt_version = None
    _fail(clipping, failure)


def _fail(clipping: Clipping, failure: Failure) -> None:
    clipping.status = "failed"
    clipping.failure_kind = failure.kind
    clipping.failure_reason = failure.reason


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
