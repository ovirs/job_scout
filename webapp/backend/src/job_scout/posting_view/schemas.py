from datetime import datetime

from pydantic import BaseModel

from job_scout.applications.models import Application
from job_scout.applications.schemas import ApplicationBriefRead
from job_scout.evaluations import domain as evaluations
from job_scout.evaluations.models import Evaluation
from job_scout.evaluations.prompt import Recommendation
from job_scout.job_postings.extraction import ExtractedFields, WorkplaceType
from job_scout.job_postings.models import JobPosting
from job_scout.llm_runs.models import RunStatus
from job_scout.llm_runs.schemas import LlmRunFailureRead
from job_scout.triage.models import Triage
from job_scout.triage.schemas import TriageRead


class ViolatedDealBreakerRead(BaseModel):
    deal_breaker_id: int
    deal_breaker_text: str
    evidence: list[str]


class EvaluationBriefRead(BaseModel):
    """What a list row shows of a posting's current (latest done) Evaluation."""

    score: int
    recommendation: Recommendation  # skip whenever a Deal Breaker is violated
    llm_recommendation: Recommendation  # the LLM's own
    summary: str
    disqualified_but_recommended: bool
    violated_deal_breakers: list[ViolatedDealBreakerRead]
    outdated: bool  # the posting's text changed since

    @classmethod
    def of(cls, run: Evaluation, posting: JobPosting) -> "EvaluationBriefRead":
        result = evaluations.checked_result(run)
        assert result is not None and run.recommendation and run.llm_recommendation
        texts = evaluations.deal_breaker_texts(run.deal_breaker_set_version)
        return cls(
            score=result.score,
            recommendation=run.recommendation,
            llm_recommendation=run.llm_recommendation,
            summary=result.summary,
            disqualified_but_recommended=bool(run.disqualified_but_recommended),
            violated_deal_breakers=[
                ViolatedDealBreakerRead(
                    deal_breaker_id=verdict.deal_breaker_id,
                    deal_breaker_text=texts[verdict.deal_breaker_id],
                    evidence=verdict.evidence,
                )
                for verdict in result.deal_breaker_verdicts
                if verdict.verdict == "violated"
            ],
            outdated=bool(evaluations.outdated(run, posting)),
        )


class JobPostingRead(BaseModel):
    id: int
    source: str
    title: str
    company: str
    location_text: str | None
    workplace_type: WorkplaceType | None
    description: str
    url: str | None
    pasted_text: str | None  # a Manual Entry's whole Clipping
    created_at: datetime
    closed_at: datetime | None
    extracted_fields: ExtractedFields | None
    evaluation_status: RunStatus | None  # the latest Evaluation's; null before any
    evaluation_failure: LlmRunFailureRead | None  # why the latest was not evaluated
    evaluation: EvaluationBriefRead | None  # the current one; null until one is done
    triage: TriageRead | None  # null while untriaged
    application: ApplicationBriefRead | None  # the live one; null while there is none

    @classmethod
    def of(
        cls,
        posting: JobPosting,
        latest_evaluation: Evaluation | None,
        *,
        current_evaluation: Evaluation | None = None,
        triage: Triage | None = None,
        application: Application | None = None,
    ) -> "JobPostingRead":
        latest = latest_evaluation
        return cls(
            id=posting.id,
            source=posting.source,
            title=posting.title,
            company=posting.company,
            location_text=posting.location_text,
            workplace_type=posting.workplace_type,
            description=posting.description,
            url=posting.url,
            pasted_text=posting.pasted_text,
            created_at=posting.created_at,
            closed_at=posting.closed_at,
            extracted_fields=posting.extracted_fields,
            evaluation_status=None if latest is None else latest.status,
            evaluation_failure=None if latest is None else LlmRunFailureRead.of(latest),
            evaluation=None
            if current_evaluation is None
            else EvaluationBriefRead.of(current_evaluation, posting),
            triage=None if triage is None else TriageRead.of(triage),
            application=None if application is None else ApplicationBriefRead.of(application),
        )
