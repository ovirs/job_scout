import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from job_scout.db import Base
from job_scout.extraction import WorkplaceType


class JobPosting(Base):
    """A Job Posting from any origin, in two layers.

    The envelope (source, company, title, location, description, dates) is set
    when the posting arrives. The extracted fields are filled by the LLM and
    stay null until extraction has run.

    Change the title, location text or description only through
    `job_scout.job_postings.set_text`, which keeps the content hash in step.
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
    source_posting_id: Mapped[str]  # generated for a manual entry
    company: Mapped[str]
    title: Mapped[str]
    location_text: Mapped[str | None]
    workplace_type: Mapped[WorkplaceType | None] = mapped_column(String)
    description: Mapped[str]
    url: Mapped[str | None]
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

    # Walking skeleton: stamped by the trivial worker task
    processed_at: Mapped[datetime | None]
