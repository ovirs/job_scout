import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from job_scout.db import Base


class Note(Base):
    """A free-text, dated note the user wrote on a Job Posting or on an Application,
    exactly one of the two. Deleting it only stamps `deleted_at`."""

    __tablename__ = "notes"
    __table_args__ = (
        CheckConstraint(
            "(job_posting_id IS NULL) <> (application_id IS NULL)", name="on_posting_or_application"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    job_posting_id: Mapped[int | None] = mapped_column(ForeignKey("job_postings.id"), index=True)
    application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id"), index=True)
    text: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    deleted_at: Mapped[datetime | None]
