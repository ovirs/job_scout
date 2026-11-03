import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from job_scout.job_postings import domain as job_postings
from job_scout.job_postings.models import JobPosting

# A route may build its response from the posting view, above it (see the import contract)
from job_scout.posting_view import domain as posting_view
from job_scout.posting_view.schemas import JobPostingRead
from job_scout.routing import Owner, Session

router = APIRouter(prefix="/api")


@router.post("/job-postings/{job_posting_id}/close")
async def close_job_posting(job_posting_id: int, session: Session, owner: Owner) -> JobPostingRead:
    """Close a posting, keeping it: a Manual Entry is closed only by the user."""
    posting = await job_posting_or_404(session, owner, job_posting_id)
    job_postings.close(posting)
    await session.commit()
    return await posting_view.read(session, posting)


@router.post("/job-postings/{job_posting_id}/reopen")
async def reopen_job_posting(job_posting_id: int, session: Session, owner: Owner) -> JobPostingRead:
    posting = await job_posting_or_404(session, owner, job_posting_id)
    job_postings.reopen(posting)
    await session.commit()
    return await posting_view.read(session, posting)


async def job_posting_or_404(
    session: AsyncSession, owner: uuid.UUID, job_posting_id: int
) -> JobPosting:
    """The owner's posting, for any package's routes; a 404 when there is none."""
    posting = await job_postings.job_posting(session, owner_id=owner, job_posting_id=job_posting_id)
    if posting is None:
        raise HTTPException(status_code=404, detail="No such Job Posting")
    return posting
