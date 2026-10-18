"""Evaluations: the LLM's judgement of a Job Posting, checked in code and gated by Deal Breakers.

Each run is its own row, kept as history. The worker gathers the current user
inputs, sends them with the posting to the LLM, checks the answer against the
Deal Breakers and the posting's own words, and applies the hard gate: any
violated Deal Breaker stores skip, whatever the LLM recommended.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from job_scout import evaluation, quotes, user_inputs
from job_scout.evaluation import (
    DealBreakerVerdict,
    EvaluationPrompt,
    EvaluationResult,
    Flag,
    PostingText,
    Recommendation,
    Verdict,
)
from job_scout.llm import Failure, Outcome
from job_scout.models import (
    DealBreakerSetVersion,
    DocumentVersion,
    Evaluation,
    EvaluationFailureKind,
    JobPosting,
)
from job_scout.quotes import EvidenceMatch

# At most this many flags of each colour
MAX_FLAGS = 5


class CheckedVerdict(DealBreakerVerdict):
    evidence_matches: list[EvidenceMatch]  # where each passage of the evidence is


class CheckedFlag(Flag):
    evidence_matches: list[EvidenceMatch]


class CheckedResult(BaseModel):
    """An `EvaluationResult` that passed every check, with where each quote was found."""

    deal_breaker_verdicts: list[CheckedVerdict]
    red_flags: list[CheckedFlag]
    green_flags: list[CheckedFlag]
    score: int
    recommendation: Recommendation
    summary: str


def queued(posting: JobPosting) -> Evaluation:
    """A new queued Evaluation of the posting; the caller enqueues its task."""
    return Evaluation(owner_id=posting.owner_id, job_posting_id=posting.id, status="queued")


@dataclass(frozen=True)
class Inputs:
    """What one run of an Evaluation is made from: the user inputs current when it ran,
    and the posting's text then."""

    career_profile: DocumentVersion | None
    preferences: DocumentVersion | None
    deal_breakers: DealBreakerSetVersion | None
    posting: PostingText
    content_hash: str

    @property
    def deal_breaker_texts(self) -> dict[int, str]:
        return deal_breaker_texts(self.deal_breakers)

    def missing(self) -> str | None:
        """Why there is nothing to judge the posting against, if there is not."""
        if self.career_profile is None or not self.career_profile.text.strip():
            return "There is no Career Profile to judge the posting against: write it first"
        return None

    def prompt(self) -> EvaluationPrompt:
        assert self.career_profile is not None
        return evaluation.prompt(
            career_profile=self.career_profile.text,
            preferences=None if self.preferences is None else self.preferences.text,
            deal_breakers=self.deal_breaker_texts,
            posting=self.posting,
        )


async def start(session: AsyncSession, run: Evaluation) -> Inputs:
    """Mark the Evaluation running and gather what it is made from."""
    run.status = "running"
    run.started_at = run.started_at or datetime.now(UTC)
    posting = await session.get_one(JobPosting, run.job_posting_id)
    owner_id = run.owner_id
    return Inputs(
        career_profile=await user_inputs.current_document(
            session, owner_id=owner_id, kind="career-profile"
        ),
        preferences=await user_inputs.current_document(
            session, owner_id=owner_id, kind="preferences"
        ),
        deal_breakers=await user_inputs.current_deal_breaker_set(session, owner_id=owner_id),
        posting=PostingText(
            title=posting.title,
            company=posting.company,
            location_text=posting.location_text,
            description=posting.description,
        ),
        content_hash=posting.content_hash,
    )


def check(outcome: Outcome[EvaluationResult], inputs: Inputs) -> Outcome[CheckedResult]:
    """The call's outcome with its result checked; a result that fails a check becomes a
    malformed failure naming what it failed."""
    result = outcome.result
    checked = result if isinstance(result, Failure) else _check(result, inputs)
    return Outcome(result=checked, model=outcome.model, prompt_version=outcome.prompt_version)


def _check(result: EvaluationResult, inputs: Inputs) -> CheckedResult | Failure:
    reason = _shape_problem(result, set(inputs.deal_breaker_texts))
    if reason is not None:
        return Failure("malformed", reason)
    verdicts = []
    for verdict in result.deal_breaker_verdicts:
        matches = _find_all(f"Deal Breaker {verdict.deal_breaker_id}", verdict.evidence, inputs)
        if isinstance(matches, Failure):
            return matches
        verdicts.append(CheckedVerdict(**verdict.model_dump(), evidence_matches=matches))
    flags: dict[str, list[CheckedFlag]] = {}
    for colour, unchecked in [("red", result.red_flags), ("green", result.green_flags)]:
        flags[colour] = []
        for flag in unchecked:
            matches = _find_all(f"A {colour} flag", flag.evidence, inputs)
            if isinstance(matches, Failure):
                return matches
            flags[colour].append(CheckedFlag(**flag.model_dump(), evidence_matches=matches))
    return CheckedResult(
        deal_breaker_verdicts=verdicts,
        red_flags=flags["red"],
        green_flags=flags["green"],
        score=result.score,
        recommendation=result.recommendation,
        summary=result.summary,
    )


def _shape_problem(result: EvaluationResult, deal_breaker_ids: set[int]) -> str | None:
    """What makes the result unusable before its quotes are looked for, if anything."""
    judged = [verdict.deal_breaker_id for verdict in result.deal_breaker_verdicts]
    for id in sorted(deal_breaker_ids):
        if judged.count(id) == 0:
            return f"The answer has no verdict for Deal Breaker {id}"
        if judged.count(id) > 1:
            return f"The answer has more than one verdict for Deal Breaker {id}"
    for id in judged:
        if id not in deal_breaker_ids:
            return f"The answer has a verdict for Deal Breaker {id}, which was not asked about"
    for verdict in result.deal_breaker_verdicts:
        if verdict.verdict != "unknown" and not verdict.evidence:
            return (
                f"The {verdict.verdict} verdict for Deal Breaker {verdict.deal_breaker_id} "
                "has no evidence"
            )
    for colour, flags in [("red", result.red_flags), ("green", result.green_flags)]:
        if any(not flag.evidence for flag in flags):
            return f"A {colour} flag has no evidence"
        if len(flags) > MAX_FLAGS:
            return f"The answer has {len(flags)} {colour} flags, more than {MAX_FLAGS}"
    if not 1 <= result.score <= 10:
        return f"The answer's score of {result.score} is not between 1 and 10"
    return None


def _find_all(what: str, passages: list[str], inputs: Inputs) -> list[EvidenceMatch] | Failure:
    """Where each passage is in the posting; a malformed failure for the first that is not."""
    matches = []
    for passage in passages:
        match = quotes.find(passage, inputs.posting)
        if match is None:
            return Failure(
                "malformed", f"{what} quotes words the posting does not contain: {passage!r}"
            )
        matches.append(match)
    return matches


def record(run: Evaluation, inputs: Inputs, outcome: Outcome[CheckedResult]) -> None:
    """Store a run's outcome: done with the gated result, or not evaluated."""
    run.model = outcome.model
    run.prompt_version = outcome.prompt_version
    _record_inputs(run, inputs)
    result = outcome.result
    if isinstance(result, Failure):
        _fail(run, result.kind, result.reason)
        return
    run.status = "done"
    run.finished_at = datetime.now(UTC)
    run.failure_kind = run.failure_reason = None
    run.result = result.model_dump(mode="json")
    # The hard gate: a violated Deal Breaker means skip, whatever the LLM recommended
    disqualified = any(v.verdict == "violated" for v in result.deal_breaker_verdicts)
    run.llm_recommendation = result.recommendation
    run.recommendation = "skip" if disqualified else result.recommendation
    run.disqualified_but_recommended = disqualified and result.recommendation != "skip"


def record_missing_input(run: Evaluation, inputs: Inputs, reason: str) -> None:
    """Store a run that had nothing to judge the posting against; no LLM was called."""
    _record_inputs(run, inputs)
    _fail(run, "missing_input", reason)


def record_failure(run: Evaluation, failure: Failure) -> None:
    """Store an error outside the LLM call, which used no model or prompt."""
    run.model = run.prompt_version = None
    _fail(run, failure.kind, failure.reason)


def _record_inputs(run: Evaluation, inputs: Inputs) -> None:
    run.career_profile_version_id = _id(inputs.career_profile)
    run.preferences_version_id = _id(inputs.preferences)
    run.deal_breaker_set_version_id = _id(inputs.deal_breakers)
    run.content_hash = inputs.content_hash


def _id(version: DocumentVersion | DealBreakerSetVersion | None) -> int | None:
    return None if version is None else version.id


def _fail(run: Evaluation, kind: EvaluationFailureKind, reason: str) -> None:
    run.status = "not_evaluated"
    run.finished_at = datetime.now(UTC)
    run.failure_kind = kind
    run.failure_reason = reason


def deal_breaker_texts(version: DealBreakerSetVersion | None) -> dict[int, str]:
    """Each Deal Breaker's text in a version of the set, by its stable id."""
    return {} if version is None else {item.deal_breaker_id: item.text for item in version.items}


def outdated(run: Evaluation, posting: JobPosting) -> bool | None:
    """Whether the posting's text changed since the Evaluation ran; None before it ran."""
    return None if run.content_hash is None else run.content_hash != posting.content_hash


def to_check(verdict: Verdict) -> bool:
    """An unknown verdict changes nothing; it is an item for the user to check."""
    return verdict == "unknown"


def checked_result(run: Evaluation) -> CheckedResult | None:
    return None if run.result is None else CheckedResult.model_validate(run.result)


async def history(
    session: AsyncSession, *, owner_id: uuid.UUID, job_posting_id: int
) -> list[Evaluation]:
    """Every Evaluation of the posting, the latest first."""
    runs = await session.scalars(
        select(Evaluation)
        .where(Evaluation.owner_id == owner_id, Evaluation.job_posting_id == job_posting_id)
        .order_by(Evaluation.id.desc())
    )
    return list(runs)


async def latest_by_posting(
    session: AsyncSession, *, owner_id: uuid.UUID, job_posting_ids: list[int]
) -> dict[int, Evaluation]:
    """The latest Evaluation of each of the postings that has one, done or not."""
    runs = await session.scalars(
        select(Evaluation)
        .where(Evaluation.owner_id == owner_id, Evaluation.job_posting_id.in_(job_posting_ids))
        .order_by(Evaluation.job_posting_id, Evaluation.id.desc())
        .ext(distinct_on(Evaluation.job_posting_id))
    )
    return {run.job_posting_id: run for run in runs}


async def current_by_posting(
    session: AsyncSession, *, owner_id: uuid.UUID, job_posting_ids: list[int]
) -> dict[int, Evaluation]:
    """The current (latest done) Evaluation of each of the postings that has one."""
    runs = await session.scalars(
        select(Evaluation)
        .where(
            Evaluation.owner_id == owner_id,
            Evaluation.job_posting_id.in_(job_posting_ids),
            Evaluation.status == "done",
        )
        .order_by(Evaluation.job_posting_id, Evaluation.id.desc())
        .ext(distinct_on(Evaluation.job_posting_id))
    )
    return {run.job_posting_id: run for run in runs}


def none_done_or_under_way(runs: list[Evaluation]) -> bool:
    """Whether a posting with this history has no Evaluation, done or under way; one
    that was not evaluated does not count."""
    return all(run.status == "not_evaluated" for run in runs)


def current(runs: list[Evaluation]) -> Evaluation | None:
    """The current Evaluation among a posting's history: the latest done one."""
    return next((run for run in runs if run.status == "done"), None)
