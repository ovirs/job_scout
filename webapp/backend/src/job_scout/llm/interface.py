"""The thin internal interface every LLM call goes through, one method per step.

Each method takes a step's inputs and returns an `Outcome`: the validated
result, or a typed `Failure`, with the model and prompt version that produced
it. It never raises for a failed call. `AnthropicLlm` is the real adapter;
`FakeLlm` replaces it in tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    # Only named in the signatures: the steps' packages sit above this interface
    from job_scout.clippings.extraction import ManualEntryExtraction
    from job_scout.cover_letters.prompt import CoverLetterPrompt, CoverLetterResult
    from job_scout.evaluations.prompt import EvaluationPrompt, EvaluationResult
    from job_scout.prompts import Prompt

FailureKind = Literal["error", "refusal", "malformed"]


@dataclass(frozen=True)
class Failure:
    """Why a call produced no result: the call failed, the model refused, or
    its answer did not have the step's shape."""

    kind: FailureKind
    reason: str


@dataclass(frozen=True)
class Outcome[T]:
    """What one LLM call produced, and with what model and prompt version."""

    result: T | Failure
    model: str
    prompt_version: str


class Llm(Protocol):
    async def extract_manual_entry(self, pasted_text: str) -> Outcome[ManualEntryExtraction]:
        """Read a Clipping's pasted text."""
        ...

    async def evaluate(self, prompt: EvaluationPrompt) -> Outcome[EvaluationResult]:
        """Judge one Job Posting against the user's inputs, as laid out in `prompt`."""
        ...

    async def write_cover_letter(
        self,
        prompt: CoverLetterPrompt,
        *,
        instructions: Prompt | None = None,
        model: str | None = None,
    ) -> Outcome[CoverLetterResult]:
        """Write a Cover Letter draft for one Job Posting, as laid out in `prompt`; with
        `instructions` or `model`, under those rather than the configured ones, as when
        trying a new prompt version or model."""
        ...
