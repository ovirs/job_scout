import uuid
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from job_scout.db import Base
from job_scout.job_postings.models import JobPosting
from job_scout.llm_runs.models import LlmRun, RunStatus, failure_complete

# A Clipping's extraction run's status, then whether the user confirmed or abandoned it
ClippingStatus = RunStatus | Literal["confirmed", "abandoned"]


class Clipping(Base, LlmRun):
    """Pasted text of a Job Posting, kept whole, on its way to becoming a Manual Entry.

    The Clipping is its own extraction run (see `llm_runs`): queued and running while
    the worker extracts it; done once the extraction and the description cut from the
    pasted text are stored; failed, with the reason, until the user retries it in place.
    Once done, the user either confirms it as a Manual Entry or abandons it; neither
    deletes it.
    """

    __tablename__ = "clippings"
    __table_args__ = (failure_complete(),)

    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    pasted_text: Mapped[str]
    url: Mapped[str | None]  # a reference, never fetched
    status: Mapped[ClippingStatus] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Once done: the LLM's `ManualEntryExtraction`, and the description cut by code
    extraction: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    description: Mapped[str | None]
    description_cut: Mapped[bool | None]  # false when the whole pasted text is the description

    # Once confirmed: the Manual Entry it became
    job_posting_id: Mapped[int | None] = mapped_column(ForeignKey("job_postings.id"), unique=True)
    job_posting: Mapped[JobPosting | None] = relationship(lazy="raise")
