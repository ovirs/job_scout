from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import APIRouter, HTTPException

from job_scout.clippings import domain as clippings
from job_scout.clippings.schemas import ClippingConfirm, ClippingRead, ClippingSubmit

# A route may build its response from the posting view, above it (see the import contract)
from job_scout.posting_view.schemas import JobPostingRead
from job_scout.routing import Owner, Session, TaskQueue

router = APIRouter(prefix="/api")


@router.post("/clippings", status_code=201)
async def submit_clipping(
    body: ClippingSubmit, session: Session, task_queue: TaskQueue, owner: Owner
) -> ClippingRead:
    """Store the pasted text as a Clipping and queue its extraction; poll it for the
    result."""
    clipping = await clippings.submit(
        session, task_queue, owner_id=owner, pasted_text=body.pasted_text, url=body.url
    )
    return ClippingRead.of(clipping)


@router.get("/clippings/{clipping_id}")
async def get_clipping(clipping_id: int, session: Session, owner: Owner) -> ClippingRead:
    with _refusals():
        clipping = await clippings.clipping(session, owner_id=owner, clipping_id=clipping_id)
    return ClippingRead.of(clipping)


@router.post("/clippings/{clipping_id}/retry")
async def retry_clipping(
    clipping_id: int, session: Session, task_queue: TaskQueue, owner: Owner
) -> ClippingRead:
    """Queue the extraction of a failed Clipping again, or of one stuck being read."""
    with _refusals():
        clipping = await clippings.retry(
            session, task_queue, owner_id=owner, clipping_id=clipping_id
        )
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
    with _refusals():
        confirmed = await clippings.confirm(
            session, task_queue, owner_id=owner, clipping_id=clipping_id, **body.model_dump()
        )
    return JobPostingRead.of(confirmed.posting, confirmed.evaluation)


@router.post("/clippings/{clipping_id}/abandon")
async def abandon_clipping(clipping_id: int, session: Session, owner: Owner) -> ClippingRead:
    """Give up on a done or failed Clipping, for instance for a similar posting already
    stored; nothing is saved as a Job Posting."""
    with _refusals():
        clipping = await clippings.abandon(session, owner_id=owner, clipping_id=clipping_id)
    return ClippingRead.of(clipping)


@contextmanager
def _refusals() -> Iterator[None]:
    """Map the Clippings package's errors to HTTP."""
    try:
        yield
    except clippings.NoSuchClipping:
        raise HTTPException(status_code=404, detail="No such Clipping") from None
    except clippings.WrongStatus as refusal:
        raise HTTPException(status_code=409, detail=str(refusal)) from None
