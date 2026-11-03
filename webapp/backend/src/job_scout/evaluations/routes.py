from fastapi import APIRouter

from job_scout import queue
from job_scout.evaluations import domain as evaluations
from job_scout.evaluations.schemas import EvaluationRead
from job_scout.job_postings.routes import job_posting_or_404
from job_scout.routing import Owner, Session, TaskQueue

router = APIRouter(prefix="/api")


@router.get("/job-postings/{job_posting_id}/evaluations")
async def list_evaluations(
    job_posting_id: int, session: Session, owner: Owner
) -> list[EvaluationRead]:
    """Every Evaluation of the posting, the latest first, each with what it was made with."""
    posting = await job_posting_or_404(session, owner, job_posting_id)
    runs = await evaluations.history(session, owner_id=owner, job_posting_id=posting.id)
    return [EvaluationRead.of(run, posting) for run in runs]


@router.get("/job-postings/{job_posting_id}/evaluations/current")
async def get_current_evaluation(
    job_posting_id: int, session: Session, owner: Owner
) -> EvaluationRead | None:
    """The posting's latest done Evaluation, or null while it has none."""
    posting = await job_posting_or_404(session, owner, job_posting_id)
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
    posting = await job_posting_or_404(session, owner, job_posting_id)
    run = evaluations.queued(posting)
    session.add(run)
    await session.commit()
    await queue.enqueue_evaluate(task_queue, run.id)
    return EvaluationRead.of(run, posting)
