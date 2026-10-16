"""The webapp's HTTP API. Serve with `uvicorn job_scout.api:create_app --factory`."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Literal

import procrastinate
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_scout import clippings, job_postings, queue, user_inputs
from job_scout.config import Settings
from job_scout.extraction import ExtractedFields, ManualEntryExtraction, WorkplaceType
from job_scout.llm import FailureKind
from job_scout.models import (
    Clipping,
    ClippingStatus,
    DealBreakerSetVersion,
    DocumentKind,
    DocumentVersion,
    JobPosting,
)
from job_scout.owners import current_owner
from job_scout.runtime import open_runtime

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class JobPostingCreate(BaseModel):
    title: NonBlank
    company: NonBlank
    location_text: NonBlank | None = None
    description: Annotated[str, Field(min_length=1)]


class JobPostingRead(BaseModel):
    id: int
    source: str
    title: str
    company: str
    location_text: str | None
    workplace_type: WorkplaceType | None
    description: str
    url: str | None
    created_at: datetime
    closed_at: datetime | None
    extracted_fields: ExtractedFields | None
    processing_status: Literal["queued", "processed"]

    @classmethod
    def of(cls, posting: JobPosting) -> "JobPostingRead":
        return cls(
            id=posting.id,
            source=posting.source,
            title=posting.title,
            company=posting.company,
            location_text=posting.location_text,
            workplace_type=posting.workplace_type,
            description=posting.description,
            url=posting.url,
            created_at=posting.created_at,
            closed_at=posting.closed_at,
            extracted_fields=posting.extracted_fields,
            processing_status="queued" if posting.processed_at is None else "processed",
        )


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
            extraction=None if clipping.status != "done" else _extraction_read(clipping),
        )


def _extraction_read(clipping: Clipping) -> ClippingExtractionRead:
    assert clipping.description is not None and clipping.description_cut is not None
    extraction = ManualEntryExtraction.model_validate(clipping.extraction)
    return ClippingExtractionRead(
        title=extraction.title,
        company=extraction.company,
        location_text=extraction.location_text,
        description=clipping.description,
        description_cut=clipping.description_cut,
        extracted_fields=extraction.extracted_fields(),
    )


class DocumentSave(BaseModel):
    # Blank is allowed: it clears the document. Whether it is required is Evaluation's concern.
    text: str


class DocumentVersionRead(BaseModel):
    id: int
    kind: DocumentKind
    number: int
    text: str
    created_at: datetime

    @classmethod
    def of(cls, version: DocumentVersion) -> "DocumentVersionRead":
        return cls(
            id=version.id,
            kind=version.kind,
            number=version.number,
            text=version.text,
            created_at=version.created_at,
        )


class DealBreakerSave(BaseModel):
    text: NonBlank


class DealBreakerRead(BaseModel):
    id: int  # stable across versions of the set
    text: str


class DealBreakerSetVersionRead(BaseModel):
    id: int
    number: int
    created_at: datetime
    deal_breakers: list[DealBreakerRead]

    @classmethod
    def of(cls, version: DealBreakerSetVersion) -> "DealBreakerSetVersionRead":
        return cls(
            id=version.id,
            number=version.number,
            created_at=version.created_at,
            deal_breakers=[
                DealBreakerRead(id=item.deal_breaker_id, text=item.text) for item in version.items
            ],
        )


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessions() as session:
        yield session


def get_task_queue(request: Request) -> procrastinate.App:
    task_queue: procrastinate.App = request.app.state.task_queue
    return task_queue


Session = Annotated[AsyncSession, Depends(get_session)]
TaskQueue = Annotated[procrastinate.App, Depends(get_task_queue)]
Owner = Annotated[uuid.UUID, Depends(current_owner)]

router = APIRouter(prefix="/api")


@router.post("/job-postings", status_code=201)
async def create_job_posting(
    body: JobPostingCreate, session: Session, task_queue: TaskQueue, owner: Owner
) -> JobPostingRead:
    posting = job_postings.new_manual_entry(owner_id=owner, **body.model_dump())
    session.add(posting)
    await session.commit()
    await queue.enqueue_mark_processed(task_queue, posting.id)
    return JobPostingRead.of(posting)


@router.get("/job-postings")
async def list_job_postings(session: Session, owner: Owner) -> list[JobPostingRead]:
    postings = await session.scalars(
        select(JobPosting)
        .where(JobPosting.owner_id == owner)
        .order_by(JobPosting.created_at.desc(), JobPosting.id.desc())
    )
    return [JobPostingRead.of(p) for p in postings]


@router.post("/clippings", status_code=201)
async def submit_clipping(
    body: ClippingSubmit, session: Session, task_queue: TaskQueue, owner: Owner
) -> ClippingRead:
    """Store the pasted text as a pending Clipping and queue its extraction; poll it for
    the result."""
    clipping = clippings.submit(owner_id=owner, pasted_text=body.pasted_text, url=body.url)
    session.add(clipping)
    await session.commit()
    await queue.enqueue_extract_clipping(task_queue, clipping.id)
    return ClippingRead.of(clipping)


@router.get("/clippings/{clipping_id}")
async def get_clipping(clipping_id: int, session: Session, owner: Owner) -> ClippingRead:
    return ClippingRead.of(await _clipping(session, owner, clipping_id))


@router.post("/clippings/{clipping_id}/retry")
async def retry_clipping(
    clipping_id: int, session: Session, task_queue: TaskQueue, owner: Owner
) -> ClippingRead:
    """Queue the extraction of a failed clipping again."""
    clipping = await _clipping(session, owner, clipping_id)
    if clipping.status != "failed":
        raise HTTPException(status_code=409, detail="Only a failed Clipping can be retried")
    clippings.retry(clipping)
    await session.commit()
    await queue.enqueue_extract_clipping(task_queue, clipping.id)
    return ClippingRead.of(clipping)


async def _clipping(session: AsyncSession, owner: uuid.UUID, clipping_id: int) -> Clipping:
    clipping = await clippings.clipping(session, owner_id=owner, clipping_id=clipping_id)
    if clipping is None:
        raise HTTPException(status_code=404, detail="No such Clipping")
    return clipping


@router.get("/documents/{kind}")
async def get_current_document(
    kind: DocumentKind, session: Session, owner: Owner
) -> DocumentVersionRead | None:
    """The current version of a document, or null while the user has not written it."""
    version = await user_inputs.current_document(session, owner_id=owner, kind=kind)
    return None if version is None else DocumentVersionRead.of(version)


@router.post("/documents/{kind}/versions", status_code=201)
async def save_document(
    kind: DocumentKind, body: DocumentSave, session: Session, owner: Owner
) -> DocumentVersionRead:
    version = await user_inputs.save_document(session, owner_id=owner, kind=kind, text=body.text)
    await session.commit()
    return DocumentVersionRead.of(version)


@router.get("/documents/{kind}/versions/{version_id}")
async def get_document_version(
    kind: DocumentKind, version_id: int, session: Session, owner: Owner
) -> DocumentVersionRead:
    version = await user_inputs.document_version(
        session, owner_id=owner, kind=kind, version_id=version_id
    )
    if version is None:
        raise HTTPException(status_code=404, detail="No such document version")
    return DocumentVersionRead.of(version)


@router.get("/deal-breakers")
async def get_current_deal_breakers(
    session: Session, owner: Owner
) -> DealBreakerSetVersionRead | None:
    """The current set of Deal Breakers, or null while the user has added none."""
    version = await user_inputs.current_deal_breaker_set(session, owner_id=owner)
    return None if version is None else DealBreakerSetVersionRead.of(version)


@router.post("/deal-breakers", status_code=201)
async def add_deal_breaker(
    body: DealBreakerSave, session: Session, owner: Owner
) -> DealBreakerSetVersionRead:
    """Add a Deal Breaker; returns the new version of the set."""
    version = await user_inputs.add_deal_breaker(session, owner_id=owner, text=body.text)
    await session.commit()
    return DealBreakerSetVersionRead.of(version)


@router.put("/deal-breakers/{deal_breaker_id}")
async def edit_deal_breaker(
    deal_breaker_id: int, body: DealBreakerSave, session: Session, owner: Owner
) -> DealBreakerSetVersionRead:
    """Change a Deal Breaker's text, keeping its id; returns the new version of the set."""
    version = await user_inputs.edit_deal_breaker(
        session, owner_id=owner, deal_breaker_id=deal_breaker_id, text=body.text
    )
    if version is None:
        raise HTTPException(status_code=404, detail="No such Deal Breaker")
    await session.commit()
    return DealBreakerSetVersionRead.of(version)


@router.delete("/deal-breakers/{deal_breaker_id}")
async def delete_deal_breaker(
    deal_breaker_id: int, session: Session, owner: Owner
) -> DealBreakerSetVersionRead:
    """Delete a Deal Breaker; returns the new version of the set, without it."""
    version = await user_inputs.delete_deal_breaker(
        session, owner_id=owner, deal_breaker_id=deal_breaker_id
    )
    if version is None:
        raise HTTPException(status_code=404, detail="No such Deal Breaker")
    await session.commit()
    return DealBreakerSetVersionRead.of(version)


@router.get("/deal-breakers/versions/{version_id}")
async def get_deal_breaker_set_version(
    version_id: int, session: Session, owner: Owner
) -> DealBreakerSetVersionRead:
    version = await user_inputs.deal_breaker_set_version(
        session, owner_id=owner, version_id=version_id
    )
    if version is None:
        raise HTTPException(status_code=404, detail="No such version of the Deal Breakers")
    return DealBreakerSetVersionRead.of(version)


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        nonlocal settings
        settings = settings or Settings()  # read from the environment
        async with open_runtime(settings) as runtime:
            app.state.sessions = runtime.sessions
            app.state.task_queue = runtime.task_queue
            yield

    app = FastAPI(
        title="Job Scout",
        lifespan=lifespan,
        # Operation ids name the generated client's functions
        generate_unique_id_function=lambda route: route.name,
    )
    app.include_router(router)
    return app
