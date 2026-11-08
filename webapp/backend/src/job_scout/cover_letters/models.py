import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import CheckConstraint, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from job_scout.db import Base
from job_scout.llm_runs.models import LlmRun, RunStatus, failure_complete
from job_scout.user_inputs.models import DocumentVersion

# Which Evaluation supplied a Cover Letter's flags: the current one, an outdated one used
# as it was, or none, when the posting had no done Evaluation
EvaluationCase = Literal["current", "outdated", "missing"]


class CoverLetterGeneration(Base, LlmRun):
    """One request to write a Cover Letter draft with the LLM: a row per request.

    Each is an LLM run (see `llm_runs`): queued, running while the worker calls the
    LLM, then done with the draft it made, or failed with the reason (locked when the
    Application left Preparing before the draft was stored); a failure makes no draft
    and leaves the Cover Letter as it was. The Evaluation whose flags it uses is fixed
    when requested, since the user confirmed that case; `evaluation_case` is the
    case confirmed, while its draft records the case when it was written. A revision in
    words also fixes, when requested, the draft whose text it sends to be revised.
    """

    __tablename__ = "cover_letter_generations"
    __table_args__ = (
        failure_complete(),
        CheckConstraint(
            "(evaluation_case = 'missing') = (evaluation_id IS NULL)", name="evaluation_case"
        ),
    )

    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    status: Mapped[RunStatus] = mapped_column(String)
    instruction: Mapped[str | None]  # typed by the user for this one letter
    evaluation_id: Mapped[int | None] = mapped_column(ForeignKey("evaluations.id"))
    evaluation_case: Mapped[EvaluationCase] = mapped_column(String)
    # The draft a revision in words revises; null when generating from scratch
    revised_draft_id: Mapped[int | None] = mapped_column(ForeignKey("cover_letter_drafts.id"))
    revised_draft: Mapped["CoverLetterDraft | None"] = relationship(
        foreign_keys=[revised_draft_id], lazy="selectin"
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Once done
    draft_id: Mapped[int | None] = mapped_column(ForeignKey("cover_letter_drafts.id"))
    draft: Mapped["CoverLetterDraft | None"] = relationship(
        foreign_keys=[draft_id], lazy="selectin"
    )


CoverLetterDraftOrigin = Literal["generated", "revised_in_words", "edited_by_hand"]


class CoverLetterDraft(Base):
    """One text of an Application's Cover Letter; the latest live draft is the letter.

    A draft is never changed afterwards. One the LLM wrote records what it was made with:
    the model, the prompt and input versions, the Evaluation that supplied its flags (or
    that none did) and the posting's content hash then. Restoring a draft copies all of
    it into a new latest draft that points back to it. Deleting it only stamps
    `deleted_at`. Its `created_at` and `deleted_at` are taken by the app, as the
    Application's `changed_at` is, since the letter sent is found by comparing them.
    """

    __tablename__ = "cover_letter_drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    origin: Mapped[CoverLetterDraftOrigin] = mapped_column(String)
    text: Mapped[str]
    instruction: Mapped[str | None]  # typed by the user for this draft
    # What the posting asks for that the Career Profile gives no support for
    unsupported_requirements: Mapped[list[str]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    deleted_at: Mapped[datetime | None]

    # What an LLM draft was made with; null for a hand edit
    model: Mapped[str | None]
    prompt_version: Mapped[str | None]
    career_profile_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_versions.id")
    )
    career_profile_version: Mapped[DocumentVersion | None] = relationship(
        foreign_keys=[career_profile_version_id], lazy="selectin"
    )
    writing_guide_version_id: Mapped[int | None] = mapped_column(ForeignKey("document_versions.id"))
    writing_guide_version: Mapped[DocumentVersion | None] = relationship(
        foreign_keys=[writing_guide_version_id], lazy="selectin"
    )
    evaluation_id: Mapped[int | None] = mapped_column(ForeignKey("evaluations.id"))
    evaluation_case: Mapped[EvaluationCase | None] = mapped_column(String)
    content_hash: Mapped[str]  # the posting's, when the draft was made
    # The earlier draft this one restores, copying its text and record
    restored_from_draft_id: Mapped[int | None] = mapped_column(ForeignKey("cover_letter_drafts.id"))
