"""One Cover Letter generation: what it is written from and how its draft is stored, and
the two rules both the request and the run check, the lock and the Career Profile.

Both `domain.py`, which requests generations, and `tasks.py`, which runs them, import
this module, so neither imports the other's rules.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from job_scout.applications.models import Application
from job_scout.cover_letters import prompt as cover_letter
from job_scout.cover_letters.models import CoverLetterDraft, CoverLetterGeneration, EvaluationCase
from job_scout.cover_letters.prompt import CoverLetterPrompt, CoverLetterResult, Flags
from job_scout.evaluations import domain as evaluations
from job_scout.evaluations.models import Evaluation
from job_scout.job_postings.models import JobPosting
from job_scout.llm.interface import Failure, Outcome
from job_scout.posting_text import PostingText
from job_scout.user_inputs import domain as user_inputs
from job_scout.user_inputs.models import DocumentVersion


def locked_reason(application: Application) -> str | None:
    """Why the Application's Cover Letter takes no change, if it does not: it changes only
    while the Application is Preparing."""
    if application.deleted_at is not None:
        return "The Application was deleted"
    if application.state != "preparing":
        return "The Application is no longer Preparing, so its Cover Letter is locked"
    return None


def missing_input(career_profile: DocumentVersion | None) -> str | None:
    """Why there is nothing to write a Cover Letter from, if there is not; the Career
    Profile is the only input required."""
    if career_profile is None or not career_profile.text.strip():
        return "There is no Career Profile to write the Cover Letter from: write it first"
    return None


@dataclass(frozen=True)
class Inputs:
    """What one run of a generation is made from: the user inputs current when it ran,
    the posting's text then, and the flags of the Evaluation fixed at the request, with
    its case judged against that text."""

    career_profile: DocumentVersion | None
    writing_guide: DocumentVersion | None
    posting: PostingText
    content_hash: str
    flags: Flags | None
    # An Evaluation current at the request is outdated if the posting changed since
    evaluation_case: EvaluationCase
    revised_text: str | None  # the draft a revision in words revises, as it was requested
    instruction: str | None

    def missing(self) -> str | None:
        """Why there is nothing to write the letter from, if there is not."""
        return missing_input(self.career_profile)

    def prompt(self) -> CoverLetterPrompt:
        assert self.career_profile is not None
        return cover_letter.prompt(
            career_profile=self.career_profile.text,
            writing_guide=None if self.writing_guide is None else self.writing_guide.text,
            posting=self.posting,
            flags=self.flags,
            draft=self.revised_text,
            instruction=self.instruction,
        )


async def gather(session: AsyncSession, generation: CoverLetterGeneration) -> Inputs:
    """What the generation is made from now."""
    application = await session.get_one(Application, generation.application_id)
    posting: JobPosting = application.job_posting
    owner_id = generation.owner_id
    flags = None
    case: EvaluationCase = "missing"
    if generation.evaluation_id is not None:
        run = await session.get_one(Evaluation, generation.evaluation_id)
        result = evaluations.checked_result(run)
        assert result is not None
        flags = Flags(
            green=[flag.point for flag in result.green_flags],
            red=[flag.point for flag in result.red_flags],
        )
        case = "outdated" if evaluations.outdated(run, posting) else "current"
    return Inputs(
        career_profile=await user_inputs.current_document(
            session, owner_id=owner_id, kind="career-profile"
        ),
        writing_guide=await user_inputs.current_document(
            session, owner_id=owner_id, kind="writing-guide"
        ),
        posting=PostingText.of(posting),
        content_hash=posting.content_hash,
        flags=flags,
        evaluation_case=case,
        revised_text=None if generation.revised_draft is None else generation.revised_draft.text,
        instruction=generation.instruction,
    )


def check(outcome: Outcome[CoverLetterResult]) -> Outcome[CoverLetterResult]:
    """The call's outcome with its result checked; a blank letter becomes a malformed
    failure."""
    result = outcome.result
    if not isinstance(result, Failure) and not result.letter.strip():
        return Outcome(
            result=Failure("malformed", "The answer's letter is blank"),
            model=outcome.model,
            prompt_version=outcome.prompt_version,
        )
    return outcome


def record(
    session: AsyncSession,
    generation: CoverLetterGeneration,
    inputs: Inputs,
    result: CoverLetterResult,
) -> None:
    """Store the letter written as a new generated draft, made with the generation's call;
    the caller holds the Application's lock."""
    draft = CoverLetterDraft(
        owner_id=generation.owner_id,
        application_id=generation.application_id,
        origin="generated" if generation.revised_draft_id is None else "revised_in_words",
        text=result.letter,
        instruction=generation.instruction,
        unsupported_requirements=result.unsupported_requirements,
        model=generation.model,
        prompt_version=generation.prompt_version,
        career_profile_version_id=_id(inputs.career_profile),
        writing_guide_version_id=_id(inputs.writing_guide),
        evaluation_id=generation.evaluation_id,
        evaluation_case=inputs.evaluation_case,
        content_hash=inputs.content_hash,
        created_at=datetime.now(UTC),
    )
    session.add(draft)
    generation.draft = draft


def _id(version: DocumentVersion | None) -> int | None:
    return None if version is None else version.id
