import uuid
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from job_scout.db import Base
from job_scout.evaluation import Recommendation
from job_scout.extraction import WorkplaceType
from job_scout.llm.interface import FailureKind

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


# Which Evaluation supplied a Cover Letter's flags: the current one, an outdated one used
# as it was, or none, when the posting had no done Evaluation
EvaluationCase = Literal["current", "outdated", "missing"]

CoverLetterGenerationStatus = Literal["queued", "running", "done", "failed"]

# Why a generation made no draft: its LLM call failed, an input it needs is missing, or
# the Application left Preparing before it ran
CoverLetterGenerationFailureKind = FailureKind | Literal["missing_input", "locked"]


class CoverLetterGeneration(Base):
    """One request to write a Cover Letter draft with the LLM: a row per request.

    Queued when requested, running while the worker calls the LLM, then done with the
    draft it made, or failed with the reason once every attempt failed; a failure makes
    no draft and leaves the Cover Letter as it was. The Evaluation whose flags it uses is
    fixed when requested, since the user confirmed that case; `evaluation_case` is the
    case confirmed, while its draft records the case when it was written. A revision in
    words also fixes, when requested, the draft whose text it sends to be revised.
    """

    __tablename__ = "cover_letter_generations"
    __table_args__ = (
        CheckConstraint(
            "(failure_kind IS NULL) = (failure_reason IS NULL)", name="failure_complete"
        ),
        CheckConstraint(
            "(evaluation_case = 'missing') = (evaluation_id IS NULL)", name="evaluation_case"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    status: Mapped[CoverLetterGenerationStatus] = mapped_column(String)
    instruction: Mapped[str | None]  # typed by the user for this one letter
    evaluation_id: Mapped[int | None] = mapped_column(ForeignKey("evaluations.id"))
    evaluation_case: Mapped[EvaluationCase] = mapped_column(String)
    # The draft a revision in words revises; null when generating from scratch
    revised_draft_id: Mapped[int | None] = mapped_column(ForeignKey("cover_letter_drafts.id"))
    revised_draft: Mapped["CoverLetterDraft | None"] = relationship(
        foreign_keys=[revised_draft_id], lazy="selectin"
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]

    # Once failed
    failure_kind: Mapped[CoverLetterGenerationFailureKind | None] = mapped_column(String)
    failure_reason: Mapped[str | None]

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
    `deleted_at`.
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
