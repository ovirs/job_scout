from datetime import datetime

from pydantic import BaseModel

from job_scout.evaluations import domain as evaluations
from job_scout.evaluations.domain import CheckedFlag
from job_scout.evaluations.models import Evaluation, EvaluationFailureKind, EvaluationStatus
from job_scout.evaluations.prompt import Recommendation, Verdict
from job_scout.evaluations.quotes import EvidenceMatch
from job_scout.job_postings.models import JobPosting
from job_scout.user_inputs.schemas import version_number


class EvaluationFailureRead(BaseModel):
    kind: EvaluationFailureKind
    reason: str


class DealBreakerVerdictRead(BaseModel):
    deal_breaker_id: int
    deal_breaker_text: str  # as worded in the version the posting was judged against
    verdict: Verdict
    evidence: list[str]  # passages from the posting
    evidence_matches: list[EvidenceMatch]  # where each passage is in the posting
    explanation: str


class EvaluationRead(BaseModel):
    id: int
    job_posting_id: int
    status: EvaluationStatus
    failure: EvaluationFailureRead | None  # why it was not evaluated
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    # What it was made with, once it ran
    model: str | None
    prompt_version: str | None
    career_profile_version_id: int | None
    preferences_version_id: int | None
    deal_breaker_set_version_id: int | None
    # The same versions numbered as the user sees them; null when the input was missing
    career_profile_version_number: int | None
    preferences_version_number: int | None
    deal_breaker_set_version_number: int | None
    outdated: bool | None  # the posting's text changed since; null until it ran

    # Once done
    summary: str | None
    score: int | None  # 1 to 10, only for ordering
    recommendation: Recommendation | None  # skip whenever a Deal Breaker is violated
    llm_recommendation: Recommendation | None  # the LLM's own
    disqualified_but_recommended: bool | None
    deal_breaker_verdicts: list[DealBreakerVerdictRead]
    to_check: list[DealBreakerVerdictRead]  # the unknown verdicts
    red_flags: list[CheckedFlag]
    green_flags: list[CheckedFlag]

    @classmethod
    def of(cls, run: Evaluation, posting: JobPosting) -> "EvaluationRead":
        result = evaluations.checked_result(run)
        texts = evaluations.deal_breaker_texts(run.deal_breaker_set_version)
        verdicts = [
            DealBreakerVerdictRead(
                deal_breaker_id=verdict.deal_breaker_id,
                deal_breaker_text=texts[verdict.deal_breaker_id],
                verdict=verdict.verdict,
                evidence=verdict.evidence,
                evidence_matches=verdict.evidence_matches,
                explanation=verdict.explanation,
            )
            for verdict in (result.deal_breaker_verdicts if result else [])
        ]
        return cls(
            id=run.id,
            job_posting_id=run.job_posting_id,
            status=run.status,
            failure=None
            if run.failure_kind is None or run.failure_reason is None
            else EvaluationFailureRead(kind=run.failure_kind, reason=run.failure_reason),
            created_at=run.created_at,
            started_at=run.started_at,
            finished_at=run.finished_at,
            model=run.model,
            prompt_version=run.prompt_version,
            career_profile_version_id=run.career_profile_version_id,
            preferences_version_id=run.preferences_version_id,
            deal_breaker_set_version_id=run.deal_breaker_set_version_id,
            career_profile_version_number=version_number(run.career_profile_version),
            preferences_version_number=version_number(run.preferences_version),
            deal_breaker_set_version_number=version_number(run.deal_breaker_set_version),
            outdated=evaluations.outdated(run, posting),
            summary=result and result.summary,
            score=result and result.score,
            recommendation=run.recommendation,
            llm_recommendation=run.llm_recommendation,
            disqualified_but_recommended=run.disqualified_but_recommended,
            deal_breaker_verdicts=verdicts,
            to_check=[verdict for verdict in verdicts if evaluations.to_check(verdict.verdict)],
            red_flags=result.red_flags if result else [],
            green_flags=result.green_flags if result else [],
        )
