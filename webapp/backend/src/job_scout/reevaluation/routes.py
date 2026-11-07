from fastapi import APIRouter

from job_scout.reevaluation import domain as reevaluation
from job_scout.reevaluation.schemas import RerunQueuedRead
from job_scout.routing import Owner, Session, TaskQueue

router = APIRouter(prefix="/api")


@router.post("/job-postings/rerun-evaluations", status_code=201)
async def rerun_unacted_evaluations(
    session: Session, task_queue: TaskQueue, owner: Owner
) -> RerunQueuedRead:
    """Queue a new Evaluation of every open posting not acted on: with no Triage and no
    live Application. Closed and acted-on postings are skipped, and so is one whose
    Evaluation is already under way."""
    runs = await reevaluation.rerun_all_unacted(session, task_queue, owner_id=owner)
    return RerunQueuedRead(queued=len(runs))
