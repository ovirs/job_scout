import uuid
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import CheckConstraint, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from job_scout.db import Base
from job_scout.job_postings.models import JobPosting
from job_scout.llm.interface import FailureKind

ClippingStatus = Literal["pending", "done", "failed", "confirmed", "abandoned"]


class Clipping(Base):
    """Pasted text of a Job Posting, kept whole, on its way to becoming a Manual Entry.

    Pending while the worker extracts it; done once the extraction and the
    description cut from the pasted text are stored; failed, with the reason, when
    every attempt failed, until the user retries. Once done, the user either
    confirms it as a Manual Entry or abandons it; neither deletes it.
    """

    __tablename__ = "clippings"
    __table_args__ = (
        CheckConstraint(
            "(failure_kind IS NULL) = (failure_reason IS NULL)", name="failure_complete"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    pasted_text: Mapped[str]
    url: Mapped[str | None]  # a reference, never fetched
    status: Mapped[ClippingStatus] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # The last extraction call, done or failed
    model: Mapped[str | None]
    prompt_version: Mapped[str | None]
    failure_kind: Mapped[FailureKind | None] = mapped_column(String)
    failure_reason: Mapped[str | None]

    # Once done: the LLM's `ManualEntryExtraction`, and the description cut by code
    extraction: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    description: Mapped[str | None]
    description_cut: Mapped[bool | None]  # false when the whole pasted text is the description

    # Once confirmed: the Manual Entry it became
    job_posting_id: Mapped[int | None] = mapped_column(ForeignKey("job_postings.id"), unique=True)
    job_posting: Mapped[JobPosting | None] = relationship(lazy="raise")
