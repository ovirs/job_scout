import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from job_scout import queue
from job_scout.clippings import domain as clippings
from job_scout.clippings.models import Clipping
from job_scout.clippings.schemas import ClippingConfirm, ClippingRead, ClippingSubmit
from job_scout.evaluations import domain as evaluations

# A route may build its response from the posting view, above it (see the import contract)
from job_scout.posting_view.schemas import JobPostingRead
from job_scout.routing import Owner, Session, TaskQueue

router = APIRouter(prefix="/api")


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
