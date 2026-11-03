import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from job_scout.db import Base

TriageValue = Literal["interested", "maybe", "ignored"]
TriageOrigin = Literal["user", "copied"]


class Triage(Base):
    """The user's own call on a Job Posting; a posting with no row is untriaged.

    At most one per posting. `created_at` is when the posting was first triaged and
    `changed_at` when the value last changed. Phase 1 only creates user-set ones;
    copied ones come with reposts and are never labels for checking Evaluations.
    """

    __tablename__ = "triages"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    job_posting_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"), unique=True)
    value: Mapped[TriageValue] = mapped_column(String)
    origin: Mapped[TriageOrigin] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    changed_at: Mapped[datetime] = mapped_column(server_default=func.now())
