import uuid
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import CheckConstraint, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from job_scout.db import Base
from job_scout.evaluations.prompt import Recommendation
from job_scout.llm.interface import FailureKind
from job_scout.user_inputs.models import DealBreakerSetVersion, DocumentVersion

EvaluationStatus = Literal["queued", "running", "done", "not_evaluated"]

# Why an Evaluation was not made: its LLM call failed, or an input it needs is missing
EvaluationFailureKind = FailureKind | Literal["missing_input"]


class Evaluation(Base):
    """One Evaluation of a Job Posting: a row per run, kept as history.

    Queued when enqueued, running while the worker calls the LLM, then done with
    the checked result, or not evaluated with the reason once every attempt
    failed. The current Evaluation of a posting is its latest done one. What it
    was made with (model, prompt and input versions, the posting's content hash)
    is recorded when it runs.
    """

    __tablename__ = "evaluations"
    __table_args__ = (
        CheckConstraint(
            "(failure_kind IS NULL) = (failure_reason IS NULL)", name="failure_complete"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    job_posting_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"), index=True)
    status: Mapped[EvaluationStatus] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]

    # What it was made with
    model: Mapped[str | None]
    prompt_version: Mapped[str | None]
    career_profile_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_versions.id")
    )
    career_profile_version: Mapped[DocumentVersion | None] = relationship(
        foreign_keys=[career_profile_version_id], lazy="selectin"
    )
    preferences_version_id: Mapped[int | None] = mapped_column(ForeignKey("document_versions.id"))
    preferences_version: Mapped[DocumentVersion | None] = relationship(
        foreign_keys=[preferences_version_id], lazy="selectin"
    )
    deal_breaker_set_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("deal_breaker_set_versions.id")
    )
    deal_breaker_set_version: Mapped[DealBreakerSetVersion | None] = relationship(lazy="selectin")
    content_hash: Mapped[str | None]  # the posting's, when it was evaluated

    # Once not evaluated
    failure_kind: Mapped[EvaluationFailureKind | None] = mapped_column(String)
    failure_reason: Mapped[str | None]

    # Once done: the checked result, with where each quote was found, and the hard gate
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    recommendation: Mapped[Recommendation | None] = mapped_column(String)  # gated
    llm_recommendation: Mapped[Recommendation | None] = mapped_column(String)
    disqualified_but_recommended: Mapped[bool | None]
