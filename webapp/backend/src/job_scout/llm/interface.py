"""The thin internal interface every LLM call goes through, one method per step.

Each method takes a step's inputs and returns an `Outcome`: the validated
result, or a typed `Failure`, with the model and prompt version that produced
it. It never raises for a failed call. `AnthropicLlm` is the real adapter;
`FakeLlm` replaces it in tests.
"""

from dataclasses import dataclass
from typing import Literal, Protocol

from job_scout.evaluation import EvaluationPrompt, EvaluationResult
from job_scout.extraction import ManualEntryExtraction

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
