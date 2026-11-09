import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from job_scout.applications import domain as applications
from job_scout.applications.models import Application
from job_scout.applications.schemas import ApplicationRead, ApplicationStateSet
from job_scout.evaluations.schemas import EvaluationRead
from job_scout.job_postings.models import JobPosting

# A route may build its response from the posting view, above it (see the import contract)
from job_scout.posting_view import domain as posting_view
from job_scout.posting_view.schemas import JobPostingRead
from job_scout.routing import Lister, Owner, Session, TaskQueue
from job_scout.settings.routes import SET_UP
from job_scout.triage.schemas import TriageSet

router = APIRouter(prefix="/api")


# The Triage route is the Applications package's, which keeps the Triage locked while the
# posting has a live Application; first, so the OpenAPI schema lists it before the others
@router.put("/job-postings/{job_posting_id}/triage")
async def set_job_posting_triage(
    job_posting_id: int, body: TriageSet, session: Session, owner: Owner
) -> JobPostingRead:
    """The user's Triage of the posting, replacing any earlier one; allowed for any
    posting, evaluated or not. Refused while the posting has a live Application, which
    keeps it locked at Interested."""
    with _refusals():
        posting = await applications.set_triage(
            session, owner_id=owner, job_posting_id=job_posting_id, value=body.value
        )
    return await posting_view.read(session, posting)


@router.post("/job-postings/{job_posting_id}/applications", status_code=201, dependencies=[SET_UP])
async def start_application(
    job_posting_id: int, session: Session, task_queue: TaskQueue, lister: Lister, owner: Owner
) -> ApplicationRead:
    """Start applying: a new Application in Preparing, with the posting's Triage set to
    Interested. Refused while the posting has a live Application. Queues an Evaluation
    of a posting that has none done or under way."""
    with _refusals():
        application = await applications.start(
            session, task_queue, lister, owner_id=owner, job_posting_id=job_posting_id
        )
    return ApplicationRead.of(application)


# The Applications package's, since the acted-on rule needs the Triage and the Application
@router.post("/evaluations/rerun-unacted", status_code=201, dependencies=[SET_UP])
async def rerun_unacted_evaluations(
    session: Session, task_queue: TaskQueue, lister: Lister, owner: Owner
) -> list[EvaluationRead]:
    """Queue a new Evaluation, with the current user inputs, of every open posting not
    acted on (with no Triage and no live Application); returns them. A posting whose
    Evaluation is already under way is left to it."""
    runs = await applications.rerun_unacted(session, task_queue, lister, owner_id=owner)
    return [
        EvaluationRead.of(run, await session.get_one(JobPosting, run.job_posting_id))
        for run in runs
    ]


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
    its history. The Cover Letter is locked outside Preparing."""
    with _refusals():
        application = await applications.move(
            session, owner_id=owner, application_id=application_id, state=body.state
        )
    return ApplicationRead.of(application)


@router.delete("/applications/{application_id}", status_code=204)
async def delete_application(application_id: int, session: Session, owner: Owner) -> None:
    """Delete an Application while it is Preparing: it is hidden everywhere but kept, and
    the posting's Triage stays Interested, changeable again. Past Preparing, an
    Application is closed rather than deleted."""
    with _refusals():
        await applications.delete(session, owner_id=owner, application_id=application_id)


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


@contextmanager
def _refusals() -> Iterator[None]:
    """Map the Applications package's errors to HTTP."""
    try:
        yield
    except applications.NoSuchJobPosting:
        raise HTTPException(status_code=404, detail="No such Job Posting") from None
    except applications.NoSuchApplication:
        raise HTTPException(status_code=404, detail="No such Application") from None
    except applications.Refused as refusal:
        raise HTTPException(status_code=409, detail=str(refusal)) from None
