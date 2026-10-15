import uuid
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from job_scout.db import Base
from job_scout.extraction import WorkplaceType

DocumentKind = Literal["career-profile", "preferences", "writing-guide"]


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


class DocumentVersion(Base):
    """One saved version of a Career Profile, Preferences or Writing Guide.

    Saving a document adds a version; a version is never changed afterwards.
    The current version of a document is the one with the highest number.
    """

    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("owner_id", "kind", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    kind: Mapped[DocumentKind] = mapped_column(String)
    number: Mapped[int]  # 1, 2, 3, ... per owner and kind
    text: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class DealBreaker(Base):
    """A Deal Breaker's identity, stable across versions of the set.

    Its text lives in the set versions, so editing it keeps its id. Deleting
    it only stamps `deleted_at` and leaves it out of the next version of the set.
    """

    __tablename__ = "deal_breakers"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    deleted_at: Mapped[datetime | None]


class DealBreakerSetVersion(Base):
    """One version of the user's Deal Breakers, versioned as a set.

    Adding, editing or deleting a Deal Breaker adds a version; a version is
    never changed afterwards. The current set is the one with the highest number.
    """

    __tablename__ = "deal_breaker_set_versions"
    __table_args__ = (UniqueConstraint("owner_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    number: Mapped[int]  # 1, 2, 3, ... per owner
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    items: Mapped[list["DealBreakerSetItem"]] = relationship(
        order_by="DealBreakerSetItem.deal_breaker_id", lazy="selectin"
    )


class DealBreakerSetItem(Base):
    """The text of one Deal Breaker in one version of the set."""

    __tablename__ = "deal_breaker_set_items"

    set_version_id: Mapped[int] = mapped_column(
        ForeignKey("deal_breaker_set_versions.id"), primary_key=True
    )
    deal_breaker_id: Mapped[int] = mapped_column(ForeignKey("deal_breakers.id"), primary_key=True)
    text: Mapped[str]
