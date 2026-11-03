from fastapi import APIRouter, HTTPException

from job_scout.applications import domain as applications
from job_scout.job_postings.routes import job_posting_or_404

# A route may build its response from the posting view, above it (see the import contract)
from job_scout.posting_view import domain as posting_view
from job_scout.posting_view.schemas import JobPostingRead
from job_scout.routing import Owner, Session
from job_scout.triage import domain as triage
from job_scout.triage.schemas import TriageSet

router = APIRouter(prefix="/api")


@router.put("/job-postings/{job_posting_id}/triage")
async def set_job_posting_triage(
    job_posting_id: int, body: TriageSet, session: Session, owner: Owner
) -> JobPostingRead:
    """The user's Triage of the posting, replacing any earlier one; allowed for any
    posting, evaluated or not. Refused while the posting has a live Application, which
    keeps it locked at Interested."""
    posting = await job_posting_or_404(session, owner, job_posting_id)
    # The Triage lock: an upward call into Applications, removed by #43
    if await applications.live(session, posting) is not None:
        raise HTTPException(
            status_code=409,
            detail="The Triage is locked at Interested while the posting has a live Application",
        )
    await triage.set_triage(session, posting, body.value)
    await session.commit()
    return await posting_view.read(session, posting)
