"""What the LLM judges a Job Posting with, and the shape of its judgement.

The prompt puts the unchanging part first so it can be cached: the user's
inputs, then the posting, last, as untrusted third-party text, laid out by
`posting_text`, which also checks every quote against it.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from job_scout.posting_text import PostingText
from job_scout.prompts import tagged

Verdict = Literal["clear", "violated", "unknown"]
Recommendation = Literal["apply", "maybe", "skip"]


class DealBreakerVerdict(BaseModel):
    deal_breaker_id: int
    verdict: Verdict
    # Passages verbatim from the posting, each its own; at least one when clear or violated
    evidence: list[str]
    explanation: str  # one sentence


class Flag(BaseModel):
    point: str  # one sentence, specific to this person
    evidence: list[str]  # passages verbatim from the posting, each its own; at least one


class EvaluationResult(BaseModel):
    """The LLM's answer. Fields are produced in this order, so evidence and verdicts
    come before the score and recommendation that rest on them."""

    deal_breaker_verdicts: list[DealBreakerVerdict]
    red_flags: list[Flag]  # at most 5
    green_flags: list[Flag]  # at most 5
    score: int  # 1 to 10, only for ordering
    recommendation: Recommendation
    summary: str  # one or two sentences


@dataclass(frozen=True)
class EvaluationPrompt:
    """The two user blocks of an Evaluation call, after the instructions."""

    user_inputs: str  # Career Profile, Preferences and numbered Deal Breakers; cacheable
    posting: str  # the Job Posting, always last

    @property
    def blocks(self) -> list[str]:
        """The blocks in the order they are sent."""
        return [self.user_inputs, self.posting]


def prompt(
    *,
    career_profile: str,
    preferences: str | None,
    deal_breakers: dict[int, str],
    posting: PostingText,
) -> EvaluationPrompt:
    """Lay out an Evaluation's inputs; `deal_breakers` is each one's text by its stable id."""
    numbered = "\n".join(f"[{id}] {text}" for id, text in sorted(deal_breakers.items()))
    user_inputs = "\n\n".join(
        [
            tagged("career_profile", career_profile),
            tagged(
                "preferences",
                (preferences or "").strip() or "(The person has written no Preferences.)",
            ),
            tagged("deal_breakers", numbered or "(The person has written no Deal Breakers.)"),
        ]
    )
    return EvaluationPrompt(user_inputs=user_inputs, posting=posting.render())
