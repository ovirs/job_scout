from fastapi import APIRouter
from sqlalchemy import select

from job_scout.fields import NonBlank
from job_scout.job_postings import domain as job_postings
from job_scout.job_postings.models import JobPosting
from job_scout.job_postings.routes import job_posting_or_404
from job_scout.posting_view import domain as posting_view
from job_scout.posting_view.domain import ListName, Sort
from job_scout.posting_view.schemas import JobPostingRead
from job_scout.routing import Owner, Session

router = APIRouter(prefix="/api")


@router.get("/job-postings")
async def list_job_postings(
    session: Session, owner: Owner, list: ListName | None = None, sort: Sort | None = None
) -> list[JobPostingRead]:
    """Every posting, the newest first; or one of the lists: inbox, skip, not-evaluated,
    shortlist, later or ignored. A list is sorted by `sort` (score or age), by default as
    its own use suits: the inbox and skip list by score, the others by age."""
    postings = await session.scalars(
        select(JobPosting)
        .where(JobPosting.owner_id == owner)
        .order_by(JobPosting.created_at.desc(), JobPosting.id.desc())
    )
    found = await posting_view.entries(session, owner_id=owner, postings=[*postings])
    if list is not None:
        found = posting_view.listing(found, list, sort)
    return [posting_view.read_of(entry) for entry in found]


# Before the route by id, which would otherwise take "similar" for an id
@router.get("/job-postings/similar")
async def find_similar_job_postings(
    company: NonBlank, title: str, session: Session, owner: Owner
) -> list[JobPostingRead]:
    """Stored postings from the same company, compared case- and whitespace-insensitively,
    the most similar title first: the possible duplicates of a posting about to be saved."""
    postings = await job_postings.similar(session, owner_id=owner, company=company, title=title)
    return await posting_view.reads(session, owner_id=owner, postings=postings)


@router.get("/job-postings/{job_posting_id}")
async def get_job_posting(job_posting_id: int, session: Session, owner: Owner) -> JobPostingRead:
    posting = await job_posting_or_404(session, owner, job_posting_id)
    return await posting_view.read(session, posting)
