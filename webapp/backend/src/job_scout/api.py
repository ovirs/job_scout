"""The webapp's HTTP API. Serve with `uvicorn job_scout.api:create_app --factory`."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Literal

import procrastinate
from fastapi import APIRouter, Depends, FastAPI, Request
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_scout import job_postings, queue
from job_scout.config import Settings
from job_scout.extraction import ExtractedFields, WorkplaceType
from job_scout.models import JobPosting
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
