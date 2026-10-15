import hashlib
import json
import uuid

from job_scout.models import JobPosting


def new_manual_entry(
    *, owner_id: uuid.UUID, company: str, title: str, location_text: str | None, description: str
) -> JobPosting:
    posting = JobPosting(
        owner_id=owner_id,
        source="manual",
        source_posting_id=str(uuid.uuid4()),
        company=company,
    )
    set_text(posting, title=title, location_text=location_text, description=description)
    return posting


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
