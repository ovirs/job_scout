import hashlib
import json
import uuid
from datetime import UTC, datetime
from difflib import SequenceMatcher

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from job_scout.job_postings.extraction import ExtractedFields, WorkplaceType
from job_scout.job_postings.models import JobPosting


def new_manual_entry(
    *,
    owner_id: uuid.UUID,
    company: str,
    title: str,
    location_text: str | None,
    workplace_type: WorkplaceType | None,
    description: str,
    url: str | None,
    pasted_text: str,
    extracted_fields: ExtractedFields,
) -> JobPosting:
    posting = JobPosting(
        owner_id=owner_id,
        source="manual",
        source_posting_id=str(uuid.uuid4()),
        company=company,
        workplace_type=workplace_type,
        url=url,
        pasted_text=pasted_text,
        extracted_fields=extracted_fields.model_dump(mode="json"),
    )
    set_text(posting, title=title, location_text=location_text, description=description)
    return posting


async def job_posting(
    session: AsyncSession, *, owner_id: uuid.UUID, job_posting_id: int
) -> JobPosting | None:
    return await session.scalar(
        select(JobPosting).where(JobPosting.id == job_posting_id, JobPosting.owner_id == owner_id)
    )


async def similar(
    session: AsyncSession, *, owner_id: uuid.UUID, company: str, title: str
) -> list[JobPosting]:
    """Stored postings from the same company, the most similar title first.

    Companies are the same when they differ only in case and whitespace, so all
    whitespace is dropped from both ("Ac me" is "ACME"). Titles are compared with
    runs of whitespace collapsed instead, since their words matter.
    """
    same_company = await session.scalars(
        select(JobPosting)
        .where(
            JobPosting.owner_id == owner_id,
            func.lower(func.regexp_replace(JobPosting.company, r"\s+", "", "g"))
            == "".join(company.split()).lower(),
        )
        .order_by(JobPosting.created_at.desc(), JobPosting.id.desc())
    )
    # A stable sort, so equally similar titles stay newest first
    return sorted(same_company, key=lambda posting: -_title_similarity(posting.title, title))


def _title_similarity(a: str, b: str) -> float:
    def normalise(text: str) -> str:
        return " ".join(text.split()).lower()

    return SequenceMatcher(None, normalise(a), normalise(b)).ratio()


def close(posting: JobPosting) -> None:
    """Mark the posting closed (the role is filled, the posting is gone); it is never
    deleted. Closing a closed posting keeps the date it first closed on."""
    if posting.closed_at is None:
        posting.closed_at = datetime.now(UTC)


def reopen(posting: JobPosting) -> None:
    posting.closed_at = None


def set_text(
    posting: JobPosting, *, title: str, location_text: str | None, description: str
) -> None:
    """The one path that changes a posting's text; it recomputes the content hash."""
    posting.title = title
    posting.location_text = location_text
    posting.description = description
    posting.content_hash = _content_hash(title, location_text, description)


def _content_hash(title: str, location_text: str | None, description: str) -> str:
    text = json.dumps([title, location_text, description])
    return hashlib.sha256(text.encode()).hexdigest()
