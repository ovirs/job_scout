from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from job_scout.clippings import domain as clippings
from job_scout.clippings.models import Clipping, ClippingStatus
from job_scout.fields import NonBlank
from job_scout.job_postings.extraction import ExtractedFields, WorkplaceType
from job_scout.llm.interface import FailureKind


class ClippingConfirm(BaseModel):
    """The envelope of the Manual Entry, as the user corrected it on the confirmation screen."""

    title: NonBlank
    company: NonBlank
    location_text: NonBlank | None = None
    workplace_type: WorkplaceType | None = None
    description: Annotated[str, Field(min_length=1, pattern=r"\S")]  # stored as given


class ClippingSubmit(BaseModel):
    pasted_text: Annotated[str, Field(min_length=1, pattern=r"\S")]  # stored as pasted
    url: NonBlank | None = None


class ExtractionFailureRead(BaseModel):
    kind: FailureKind
    reason: str


class ClippingExtractionRead(BaseModel):
    title: str | None
    company: str | None
    location_text: str | None
    description: str  # cut from the pasted text, never written by the LLM
    description_cut: bool  # false when the markers were not found: the whole pasted text
    extracted_fields: ExtractedFields


class ClippingRead(BaseModel):
    id: int
    status: ClippingStatus
    pasted_text: str
    url: str | None
    created_at: datetime
    model: str | None
    prompt_version: str | None
    failure: ExtractionFailureRead | None
    extraction: ClippingExtractionRead | None
    job_posting_id: int | None  # the Manual Entry it was confirmed as

    @classmethod
    def of(cls, clipping: Clipping) -> "ClippingRead":
        return cls(
            id=clipping.id,
            status=clipping.status,
            pasted_text=clipping.pasted_text,
            url=clipping.url,
            created_at=clipping.created_at,
            model=clipping.model,
            prompt_version=clipping.prompt_version,
            failure=None
            if clipping.failure_kind is None or clipping.failure_reason is None
            else ExtractionFailureRead(kind=clipping.failure_kind, reason=clipping.failure_reason),
            extraction=None if clipping.extraction is None else _extraction_read(clipping),
            job_posting_id=clipping.job_posting_id,
        )


def _extraction_read(clipping: Clipping) -> ClippingExtractionRead:
    assert clipping.description is not None and clipping.description_cut is not None
    extraction = clippings.extraction(clipping)
    return ClippingExtractionRead(
        title=extraction.title,
        company=extraction.company,
        location_text=extraction.location_text,
        description=clipping.description,
        description_cut=clipping.description_cut,
        extracted_fields=extraction.extracted_fields(),
    )
