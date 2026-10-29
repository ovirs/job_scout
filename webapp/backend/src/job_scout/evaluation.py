"""What the LLM judges a Job Posting with, and the shape of its judgement.

The prompt puts the unchanging part first so it can be cached: the user's
inputs, then the posting, last, as untrusted third-party text. The posting is
its own text only: title, company, location and description, the text every
quote must come from. Extracted fields never feed the Evaluation (ADR 0003),
nor does the workplace type, which is one of them.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

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
class PostingText:
    """The part of a Job Posting the Evaluation reads, and the text its quotes must come from."""

    title: str
    company: str
    location_text: str | None
    description: str


# The label each field gets in the prompt. The posting does not contain these words, but
# a model may quote a field with its label, so the quote check accepts it (see `quotes`).
POSTING_LABELS = {
    "title": "Title:",
    "company": "Company:",
    "location_text": "Location:",
    "description": "Description:",
}


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
            _tagged("career_profile", career_profile),
            _tagged(
                "preferences",
                (preferences or "").strip() or "(The person has written no Preferences.)",
            ),
            _tagged("deal_breakers", numbered or "(The person has written no Deal Breakers.)"),
        ]
    )
    lines = [
        f"{POSTING_LABELS['title']} {posting.title}",
        f"{POSTING_LABELS['company']} {posting.company}",
    ]
    if posting.location_text:
        lines.append(f"{POSTING_LABELS['location_text']} {posting.location_text}")
    lines += [POSTING_LABELS["description"], posting.description]
    return EvaluationPrompt(
        user_inputs=user_inputs, posting=_tagged("job_posting", "\n".join(lines))
    )


def _tagged(tag: str, text: str) -> str:
    return f"<{tag}>\n{text.strip()}\n</{tag}>"
