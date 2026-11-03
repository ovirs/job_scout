import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from job_scout import queue
from job_scout.applications import domain as applications
from job_scout.applications.models import Application
from job_scout.applications.schemas import ApplicationRead, ApplicationStateSet
from job_scout.cover_letters import domain as cover_letters
from job_scout.evaluations import domain as evaluations
from job_scout.job_postings.routes import job_posting_or_404
from job_scout.routing import Owner, Session, TaskQueue
from job_scout.triage import domain as triage

router = APIRouter(prefix="/api")


@router.post("/job-postings/{job_posting_id}/applications", status_code=201)
async def start_application(
    job_posting_id: int, session: Session, task_queue: TaskQueue, owner: Owner
) -> ApplicationRead:
    """Start applying: a new Application in Preparing, with the posting's Triage set to
    Interested. Refused while the posting has a live Application. Queues an Evaluation
    of a posting that has none done or under way."""
    posting = await job_posting_or_404(session, owner, job_posting_id)
    if await applications.live(session, posting) is not None:
        raise HTTPException(status_code=409, detail="The posting already has a live Application")
    await triage.set_triage(session, posting, "interested")
    application = applications.start(posting)
    session.add(application)
    runs = await evaluations.history(session, owner_id=owner, job_posting_id=posting.id)
    run = evaluations.queued(posting) if evaluations.none_done_or_under_way(runs) else None
    if run is not None:
        session.add(run)
    await session.commit()
    if run is not None:
        await queue.enqueue_evaluate(task_queue, run.id)
    return ApplicationRead.of(application)


@router.get("/applications")
async def list_applications(
    session: Session, owner: Owner, closed: bool | None = None
) -> list[ApplicationRead]:
    """The live Applications by state, Preparing to No response, the latest move first
    within a state; with `closed`, only the closed ones (Accepted, Rejected, Withdrawn, No
    response) or only those in flight."""
    found = await applications.by_state(session, owner_id=owner, closed=closed)
    return [ApplicationRead.of(application) for application in found]


@router.get("/applications/{application_id}")
async def get_application(application_id: int, session: Session, owner: Owner) -> ApplicationRead:
    return ApplicationRead.of(await application_or_404(session, owner, application_id))


@router.put("/applications/{application_id}/state")
async def set_application_state(
    application_id: int, body: ApplicationStateSet, session: Session, owner: Owner
) -> ApplicationRead:
    """Move the Application to any state, from any other; each move is kept, dated, in
    its history. The Cover Letter is locked outside Preparing, and each move to Applied
    records its latest draft as the letter sent, or that no letter was sent."""
    application = await application_or_404(session, owner, application_id)
    change = applications.set_state(application, body.state)
    if change is not None:
        # An upward call into Cover Letters, removed by #42
        await cover_letters.lock_sent(session, application, change)
    await session.commit()
    return ApplicationRead.of(application)


@router.delete("/applications/{application_id}", status_code=204)
async def delete_application(application_id: int, session: Session, owner: Owner) -> None:
    """Delete an Application while it is Preparing: it is hidden everywhere but kept, and
    the posting's Triage stays Interested, changeable again. Past Preparing, an
    Application is closed rather than deleted."""
    application = await application_or_404(session, owner, application_id)
    if application.state != "preparing":
        raise HTTPException(
            status_code=409, detail="Only an Application in Preparing can be deleted"
        )
    applications.delete(application)
    await session.commit()


async def application_or_404(
    session: AsyncSession, owner: uuid.UUID, application_id: int
) -> Application:
    """The owner's live Application, for any package's routes; a 404 when there is none."""
    application = await applications.application(
        session, owner_id=owner, application_id=application_id
    )
    if application is None:
        raise HTTPException(status_code=404, detail="No such Application")
    return application
