from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from job_scout.clippings import domain as clippings
from job_scout.clippings.models import Clipping, ClippingStatus
from job_scout.fields import NonBlank
from job_scout.job_postings.extraction import ExtractedFields, WorkplaceType
from job_scout.llm.interface import Provider
from job_scout.llm_runs import domain as llm_runs
from job_scout.llm_runs.schemas import LlmRunFailureRead, LlmRunStart, model_choice_read
from job_scout.settings.schemas import ModelChoiceBody


class ClippingConfirm(BaseModel):
    """The envelope of the Manual Entry, as the user corrected it on the confirmation screen."""

    title: NonBlank
    company: NonBlank
    location_text: NonBlank | None = None
    workplace_type: WorkplaceType | None = None
    description: Annotated[str, Field(min_length=1, pattern=r"\S")]  # stored as given


class ClippingSubmit(LlmRunStart):
    pasted_text: Annotated[str, Field(min_length=1, pattern=r"\S")]  # stored as pasted
    url: NonBlank | None = None


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
    stuck: bool  # queued or running for too long: retry it
    pasted_text: str
    url: str | None
    created_at: datetime
    started_at: datetime | None  # when its extraction first started
    finished_at: datetime | None
    model_choice: ModelChoiceBody | None  # what it was queued with; a retry keeps it
    provider: Provider | None  # the Provider that answered, and the model it reported
    model: str | None
    prompt_version: str | None
    failure: LlmRunFailureRead | None
    extraction: ClippingExtractionRead | None
    job_posting_id: int | None  # the Manual Entry it was confirmed as

    @classmethod
    def of(cls, clipping: Clipping) -> "ClippingRead":
        return cls(
            id=clipping.id,
            status=clipping.status,
            stuck=llm_runs.stuck(clipping),
            pasted_text=clipping.pasted_text,
            url=clipping.url,
            created_at=clipping.created_at,
            started_at=clipping.started_at,
            finished_at=clipping.finished_at,
            model_choice=model_choice_read(clipping),
            provider=clipping.provider,
            model=clipping.model,
            prompt_version=clipping.prompt_version,
            failure=LlmRunFailureRead.of(clipping),
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
