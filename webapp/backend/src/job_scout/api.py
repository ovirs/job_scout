"""The webapp's HTTP API. Serve with `uvicorn job_scout.api:create_app --factory`."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated

import procrastinate
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_scout import clippings, evaluations, job_postings, queue, user_inputs
from job_scout.config import Settings
from job_scout.evaluation import Recommendation, Verdict
from job_scout.evaluations import CheckedFlag
from job_scout.extraction import ExtractedFields, WorkplaceType
from job_scout.llm import FailureKind
from job_scout.models import (
    Clipping,
    ClippingStatus,
    DealBreakerSetVersion,
    DocumentKind,
    DocumentVersion,
    Evaluation,
    EvaluationFailureKind,
    EvaluationStatus,
    JobPosting,
)
from job_scout.owners import current_owner
from job_scout.quotes import EvidenceMatch
from job_scout.runtime import open_runtime

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ClippingConfirm(BaseModel):
    """The envelope of the Manual Entry, as the user corrected it on the confirmation screen."""

    title: NonBlank
    company: NonBlank
    location_text: NonBlank | None = None
    workplace_type: WorkplaceType | None = None
    description: Annotated[str, Field(min_length=1, pattern=r"\S")]  # stored as given


class JobPostingRead(BaseModel):
    id: int
    source: str
    title: str
    company: str
    location_text: str | None
    workplace_type: WorkplaceType | None
    description: str
    url: str | None
    pasted_text: str | None  # a Manual Entry's whole Clipping
    created_at: datetime
    closed_at: datetime | None
    extracted_fields: ExtractedFields | None
    evaluation_status: EvaluationStatus | None  # the latest Evaluation's; null before any

    @classmethod
    def of(cls, posting: JobPosting, latest_evaluation: Evaluation | None) -> "JobPostingRead":
        return cls(
            id=posting.id,
            source=posting.source,
            title=posting.title,
            company=posting.company,
            location_text=posting.location_text,
            workplace_type=posting.workplace_type,
            description=posting.description,
            url=posting.url,
            pasted_text=posting.pasted_text,
            created_at=posting.created_at,
            closed_at=posting.closed_at,
            extracted_fields=posting.extracted_fields,
            evaluation_status=None if latest_evaluation is None else latest_evaluation.status,
        )


class EvaluationFailureRead(BaseModel):
    kind: EvaluationFailureKind
    reason: str


class DealBreakerVerdictRead(BaseModel):
    deal_breaker_id: int
    deal_breaker_text: str  # as worded in the version the posting was judged against
    verdict: Verdict
    evidence: list[str]  # passages from the posting
    evidence_matches: list[EvidenceMatch]  # where each passage is in the posting
    explanation: str


class EvaluationRead(BaseModel):
    id: int
    job_posting_id: int
    status: EvaluationStatus
    failure: EvaluationFailureRead | None  # why it was not evaluated
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    # What it was made with, once it ran
    model: str | None
    prompt_version: str | None
    career_profile_version_id: int | None
    preferences_version_id: int | None
    deal_breaker_set_version_id: int | None
    # The same versions numbered as the user sees them; null when the input was missing
    career_profile_version_number: int | None
    preferences_version_number: int | None
    deal_breaker_set_version_number: int | None
    outdated: bool | None  # the posting's text changed since; null until it ran

    # Once done
    summary: str | None
    score: int | None  # 1 to 10, only for ordering
    recommendation: Recommendation | None  # skip whenever a Deal Breaker is violated
    llm_recommendation: Recommendation | None  # the LLM's own
    disqualified_but_recommended: bool | None
    deal_breaker_verdicts: list[DealBreakerVerdictRead]
    to_check: list[DealBreakerVerdictRead]  # the unknown verdicts
    red_flags: list[CheckedFlag]
    green_flags: list[CheckedFlag]

    @classmethod
    def of(cls, run: Evaluation, posting: JobPosting) -> "EvaluationRead":
        result = evaluations.checked_result(run)
        texts = evaluations.deal_breaker_texts(run.deal_breaker_set_version)
        verdicts = [
            DealBreakerVerdictRead(
                deal_breaker_id=verdict.deal_breaker_id,
                deal_breaker_text=texts[verdict.deal_breaker_id],
                verdict=verdict.verdict,
                evidence=verdict.evidence,
                evidence_matches=verdict.evidence_matches,
                explanation=verdict.explanation,
            )
            for verdict in (result.deal_breaker_verdicts if result else [])
        ]
        return cls(
            id=run.id,
            job_posting_id=run.job_posting_id,
            status=run.status,
            failure=None
            if run.failure_kind is None or run.failure_reason is None
            else EvaluationFailureRead(kind=run.failure_kind, reason=run.failure_reason),
            created_at=run.created_at,
            started_at=run.started_at,
            finished_at=run.finished_at,
            model=run.model,
            prompt_version=run.prompt_version,
            career_profile_version_id=run.career_profile_version_id,
            preferences_version_id=run.preferences_version_id,
            deal_breaker_set_version_id=run.deal_breaker_set_version_id,
            career_profile_version_number=_version_number(run.career_profile_version),
            preferences_version_number=_version_number(run.preferences_version),
            deal_breaker_set_version_number=_version_number(run.deal_breaker_set_version),
            outdated=evaluations.outdated(run, posting),
            summary=result and result.summary,
            score=result and result.score,
            recommendation=run.recommendation,
            llm_recommendation=run.llm_recommendation,
            disqualified_but_recommended=run.disqualified_but_recommended,
            deal_breaker_verdicts=verdicts,
            to_check=[verdict for verdict in verdicts if evaluations.to_check(verdict.verdict)],
            red_flags=result.red_flags if result else [],
            green_flags=result.green_flags if result else [],
        )


def _version_number(version: DocumentVersion | DealBreakerSetVersion | None) -> int | None:
    return None if version is None else version.number


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


@router.get("/job-postings")
async def list_job_postings(session: Session, owner: Owner) -> list[JobPostingRead]:
    postings = await session.scalars(
        select(JobPosting)
        .where(JobPosting.owner_id == owner)
        .order_by(JobPosting.created_at.desc(), JobPosting.id.desc())
    )
    return await _job_posting_reads(session, owner, list(postings))


@router.get("/job-postings/similar")
async def find_similar_job_postings(
    company: NonBlank, title: str, session: Session, owner: Owner
) -> list[JobPostingRead]:
    """Stored postings from the same company, compared case- and whitespace-insensitively,
    the most similar title first: the possible duplicates of a posting about to be saved."""
    postings = await job_postings.similar(session, owner_id=owner, company=company, title=title)
    return await _job_posting_reads(session, owner, postings)


@router.get("/job-postings/{job_posting_id}")
async def get_job_posting(job_posting_id: int, session: Session, owner: Owner) -> JobPostingRead:
    posting = await _job_posting(session, owner, job_posting_id)
    return await _job_posting_read(session, owner, posting)


@router.post("/job-postings/{job_posting_id}/close")
async def close_job_posting(job_posting_id: int, session: Session, owner: Owner) -> JobPostingRead:
    """Close a posting, keeping it: a Manual Entry is closed only by the user."""
    posting = await _job_posting(session, owner, job_posting_id)
    job_postings.close(posting)
    await session.commit()
    return await _job_posting_read(session, owner, posting)


@router.post("/job-postings/{job_posting_id}/reopen")
async def reopen_job_posting(job_posting_id: int, session: Session, owner: Owner) -> JobPostingRead:
    posting = await _job_posting(session, owner, job_posting_id)
    job_postings.reopen(posting)
    await session.commit()
    return await _job_posting_read(session, owner, posting)


@router.get("/job-postings/{job_posting_id}/evaluations")
async def list_evaluations(
    job_posting_id: int, session: Session, owner: Owner
) -> list[EvaluationRead]:
    """Every Evaluation of the posting, the latest first, each with what it was made with."""
    posting = await _job_posting(session, owner, job_posting_id)
    runs = await evaluations.history(session, owner_id=owner, job_posting_id=posting.id)
    return [EvaluationRead.of(run, posting) for run in runs]


@router.get("/job-postings/{job_posting_id}/evaluations/current")
async def get_current_evaluation(
    job_posting_id: int, session: Session, owner: Owner
) -> EvaluationRead | None:
    """The posting's latest done Evaluation, or null while it has none."""
    posting = await _job_posting(session, owner, job_posting_id)
    runs = await evaluations.history(session, owner_id=owner, job_posting_id=posting.id)
    current = evaluations.current(runs)
    return None if current is None else EvaluationRead.of(current, posting)


@router.post("/job-postings/{job_posting_id}/evaluations", status_code=201)
async def rerun_evaluation(
    job_posting_id: int, session: Session, task_queue: TaskQueue, owner: Owner
) -> EvaluationRead:
    """Queue a new Evaluation of the posting, with the current user inputs; earlier ones
    are kept as history. Also the retry of one that was not evaluated, and allowed while
    another is under way, so one stuck by a crashed worker never blocks it."""
    posting = await _job_posting(session, owner, job_posting_id)
    run = evaluations.queued(posting)
    session.add(run)
    await session.commit()
    await queue.enqueue_evaluate(task_queue, run.id)
    return EvaluationRead.of(run, posting)


async def _job_posting_read(
    session: AsyncSession, owner: uuid.UUID, posting: JobPosting
) -> JobPostingRead:
    return (await _job_posting_reads(session, owner, [posting]))[0]


async def _job_posting_reads(
    session: AsyncSession, owner: uuid.UUID, postings: list[JobPosting]
) -> list[JobPostingRead]:
    latest = await evaluations.latest_by_posting(
        session, owner_id=owner, job_posting_ids=[p.id for p in postings]
    )
    return [JobPostingRead.of(p, latest.get(p.id)) for p in postings]


async def _job_posting(session: AsyncSession, owner: uuid.UUID, job_posting_id: int) -> JobPosting:
    posting = await job_postings.job_posting(session, owner_id=owner, job_posting_id=job_posting_id)
    if posting is None:
        raise HTTPException(status_code=404, detail="No such Job Posting")
    return posting


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


@router.post("/clippings/{clipping_id}/confirm", status_code=201)
async def confirm_clipping(
    clipping_id: int,
    body: ClippingConfirm,
    session: Session,
    task_queue: TaskQueue,
    owner: Owner,
) -> JobPostingRead:
    """Save a done Clipping as a Manual Entry, with the user's corrections."""
    clipping = await _clipping(session, owner, clipping_id, for_update=True)
    if clipping.status != "done":
        raise HTTPException(status_code=409, detail="Only a done Clipping can be confirmed")
    posting = clippings.confirm(clipping, **body.model_dump())
    session.add(posting)
    await session.flush()  # assigns the posting's id
    run = evaluations.queued(posting)
    session.add(run)
    await session.commit()
    await queue.enqueue_evaluate(task_queue, run.id)
    return JobPostingRead.of(posting, run)


@router.post("/clippings/{clipping_id}/abandon")
async def abandon_clipping(clipping_id: int, session: Session, owner: Owner) -> ClippingRead:
    """Give up on a done or failed Clipping, for instance for a similar posting already
    stored; nothing is saved as a Job Posting."""
    clipping = await _clipping(session, owner, clipping_id, for_update=True)
    if clipping.status not in ("done", "failed"):
        raise HTTPException(
            status_code=409, detail="Only a done or failed Clipping can be abandoned"
        )
    clippings.abandon(clipping)
    await session.commit()
    return ClippingRead.of(clipping)


async def _clipping(
    session: AsyncSession, owner: uuid.UUID, clipping_id: int, *, for_update: bool = False
) -> Clipping:
    clipping = await clippings.clipping(
        session, owner_id=owner, clipping_id=clipping_id, for_update=for_update
    )
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
