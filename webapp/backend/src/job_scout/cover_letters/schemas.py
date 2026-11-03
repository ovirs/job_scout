from datetime import datetime

from pydantic import BaseModel

from job_scout.cover_letters.models import (
    CoverLetterDraft,
    CoverLetterDraftOrigin,
    CoverLetterGeneration,
    CoverLetterGenerationFailureKind,
    CoverLetterGenerationStatus,
    EvaluationCase,
)
from job_scout.fields import NonBlank
from job_scout.user_inputs.schemas import version_number


class CoverLetterGenerate(BaseModel):
    """A request for a new draft. `evaluation_case` is the case of the posting's Evaluation
    the user was told of and agreed to; a request naming another case is refused."""

    evaluation_case: EvaluationCase
    instruction: NonBlank | None = None  # what to stress, the language to write in


class CoverLetterRevise(BaseModel):
    """A request to revise the latest draft, hand edits included, as `instruction` says,
    from the same inputs as generating; `evaluation_case` as for generating."""

    evaluation_case: EvaluationCase
    instruction: NonBlank  # what to change: "shorter, and lead with the Kafka migration"


class CoverLetterEvaluationRead(BaseModel):
    """Which Evaluation's flags a draft generated now would use: the current one, an
    outdated one as it is, or none (missing). Ask the user to confirm the last two."""

    case: EvaluationCase
    evaluation_id: int | None  # null when missing


class CoverLetterDraftRead(BaseModel):
    id: int
    origin: CoverLetterDraftOrigin
    text: str
    instruction: str | None
    unsupported_requirements: list[str]  # what the posting asks for that the profile lacks
    created_at: datetime

    # What an LLM draft was made with
    model: str | None
    prompt_version: str | None
    career_profile_version_id: int | None
    career_profile_version_number: int | None
    writing_guide_version_id: int | None
    writing_guide_version_number: int | None  # null when there was no Writing Guide
    evaluation_id: int | None  # whose flags it used; null when there was none
    evaluation_case: EvaluationCase | None
    restored_from_draft_id: int | None  # the earlier draft it copies, when restored

    @classmethod
    def of(cls, draft: CoverLetterDraft) -> "CoverLetterDraftRead":
        return cls(
            id=draft.id,
            origin=draft.origin,
            text=draft.text,
            instruction=draft.instruction,
            unsupported_requirements=draft.unsupported_requirements,
            created_at=draft.created_at,
            model=draft.model,
            prompt_version=draft.prompt_version,
            career_profile_version_id=draft.career_profile_version_id,
            career_profile_version_number=version_number(draft.career_profile_version),
            writing_guide_version_id=draft.writing_guide_version_id,
            writing_guide_version_number=version_number(draft.writing_guide_version),
            evaluation_id=draft.evaluation_id,
            evaluation_case=draft.evaluation_case,
            restored_from_draft_id=draft.restored_from_draft_id,
        )


class CoverLetterGenerationFailureRead(BaseModel):
    kind: CoverLetterGenerationFailureKind
    reason: str


class CoverLetterGenerationRead(BaseModel):
    id: int
    status: CoverLetterGenerationStatus
    instruction: str | None
    evaluation_case: EvaluationCase
    revised_draft_id: int | None  # the draft a revision in words revises; null for generating
    failure: CoverLetterGenerationFailureRead | None  # why it made no draft
    created_at: datetime
    finished_at: datetime | None
    draft_id: int | None  # the draft it made, once done

    @classmethod
    def of(cls, generation: CoverLetterGeneration) -> "CoverLetterGenerationRead":
        return cls(
            id=generation.id,
            status=generation.status,
            instruction=generation.instruction,
            evaluation_case=generation.evaluation_case,
            revised_draft_id=generation.revised_draft_id,
            failure=None
            if generation.failure_kind is None or generation.failure_reason is None
            else CoverLetterGenerationFailureRead(
                kind=generation.failure_kind, reason=generation.failure_reason
            ),
            created_at=generation.created_at,
            finished_at=generation.finished_at,
            draft_id=generation.draft_id,
        )


class CoverLetterDraftSave(BaseModel):
    text: NonBlank  # the whole letter, as the user edited it


class SentCoverLetterRead(BaseModel):
    """The Cover Letter sent on the latest move to Applied."""

    applied_at: datetime
    draft: CoverLetterDraftRead | None  # null when no Cover Letter was sent


class CoverLetterRead(BaseModel):
    application_id: int
    editable: bool  # only while the Application is Preparing
    draft: CoverLetterDraftRead | None  # the letter: its latest draft; null before any
    drafts: list[CoverLetterDraftRead]  # every live draft, the latest first
    posting_edited_since_draft: bool | None  # the posting's text changed; null with no draft
    sent: SentCoverLetterRead | None  # null until the Application first moves to Applied
    generation: CoverLetterGenerationRead | None  # the latest request, done or not
    evaluation: CoverLetterEvaluationRead  # what generating now would take flags from
