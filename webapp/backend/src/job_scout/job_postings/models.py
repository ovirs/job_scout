import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from job_scout.db import Base
from job_scout.job_postings.extraction import WorkplaceType


class JobPosting(Base):
    """A Job Posting from any origin, in two layers.

    The envelope (source, company, title, location, description, dates) is set
    when the posting arrives. The extracted fields are filled by the LLM and
    stay null until extraction has run.

    Change a stored posting's title, location text or description only through
    `job_scout.applications.domain.update_text`, its update path, which keeps the content
    hash in step and applies the re-evaluation rule; a new posting's are set with
    `job_scout.job_postings.domain.set_text`.
    """

    __tablename__ = "job_postings"
    __table_args__ = (
        UniqueConstraint("ats", "ats_board", "ats_posting_id"),
        CheckConstraint(
            "(ats IS NULL) = (ats_board IS NULL) AND (ats IS NULL) = (ats_posting_id IS NULL)",
            name="ats_key_complete",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)

    # Envelope
    source: Mapped[str]  # "manual" in phase 1; ATS names later
    source_posting_id: Mapped[str]  # generated for a Manual Entry
    company: Mapped[str]
    title: Mapped[str]
    location_text: Mapped[str | None]
    workplace_type: Mapped[WorkplaceType | None] = mapped_column(String)
    description: Mapped[str]
    url: Mapped[str | None]  # a reference, never fetched
    pasted_text: Mapped[str | None]  # a Manual Entry's whole Clipping, kept next to it
    content_hash: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    closed_at: Mapped[datetime | None]

    # Extracted fields: an `ExtractedFields`, null until extraction has run
    extracted_fields: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # Ready for Pipelines, unused in phase 1
    ats: Mapped[str | None]
    ats_board: Mapped[str | None]
    ats_posting_id: Mapped[str | None]
    raw_ats_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    screening_scores: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    screened_in: Mapped[bool | None]  # null for manual entries, which skip screening
    repost_of_id: Mapped[int | None] = mapped_column(ForeignKey("job_postings.id"))
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("job_postings.id"))
