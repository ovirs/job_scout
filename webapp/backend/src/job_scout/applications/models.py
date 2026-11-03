import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from job_scout.db import Base
from job_scout.job_postings.models import JobPosting

if TYPE_CHECKING:
    # A relationship up to Cover Letters (ADR-0004); removed by #42
    from job_scout.cover_letters.models import CoverLetterDraft

ApplicationState = Literal[
    "preparing",
    "applied",
    "screen_call",
    "interview_loop",
    "offer",
    "accepted",
    "rejected",
    "withdrawn",
    "no_response",
]


class Application(Base):
    """The user's tracked progress in applying for one Job Posting.

    Its state is set by hand, any state to any other, each change kept in its history.
    On the first move to Applied it takes a copy of the posting (`copy_*`), which never
    changes afterwards. Deleting it, allowed only while Preparing, only stamps
    `deleted_at`; a posting has at most one live (not deleted) Application.
    """

    __tablename__ = "applications"
    __table_args__ = (
        Index(
            "ix_applications_one_live_per_posting",
            "job_posting_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint(
            "(copied_at IS NULL) = (copy_title IS NULL)"
            " AND (copied_at IS NULL) = (copy_company IS NULL)"
            " AND (copied_at IS NULL) = (copy_description IS NULL)"
            " AND (copied_at IS NULL) = (copy_content_hash IS NULL)",
            name="posting_copy_complete",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    job_posting_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"), index=True)
    job_posting: Mapped[JobPosting] = relationship(lazy="selectin")
    state: Mapped[ApplicationState] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    deleted_at: Mapped[datetime | None]

    # The posting as it was on the first move to Applied
    copied_at: Mapped[datetime | None]
    copy_title: Mapped[str | None]
    copy_company: Mapped[str | None]
    copy_location_text: Mapped[str | None]
    copy_description: Mapped[str | None]
    copy_url: Mapped[str | None]
    copy_content_hash: Mapped[str | None]

    history: Mapped[list["ApplicationStateChange"]] = relationship(
        order_by="ApplicationStateChange.id", lazy="selectin"
    )


class ApplicationStateChange(Base):
    """One entry in an Application's state history: the state it moved to, and when.
    Starting an Application records its first entry, Preparing. A move to Applied also
    records the Cover Letter sent: the latest draft then, or none."""

    __tablename__ = "application_state_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    state: Mapped[ApplicationState] = mapped_column(String)
    changed_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # On a move to Applied, the draft locked as the letter sent; null when none was
    sent_draft_id: Mapped[int | None] = mapped_column(ForeignKey("cover_letter_drafts.id"))
    sent_draft: Mapped["CoverLetterDraft | None"] = relationship(lazy="selectin")
