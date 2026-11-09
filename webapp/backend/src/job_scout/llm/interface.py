"""The thin internal interface every LLM call goes through, one method per step.

Each method takes a step's inputs and returns an `Outcome`: the validated
result, or a typed `Failure`, with the model and prompt version that produced
it. It never raises for a failed call. `AnthropicLlm` is the real adapter;
`FakeLlm` replaces it in tests.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    # Only named in the signatures: the steps' packages sit above this interface
    from job_scout.clippings.extraction import ManualEntryExtraction
    from job_scout.cover_letters.prompt import CoverLetterPrompt, CoverLetterResult
    from job_scout.evaluations.prompt import EvaluationPrompt, EvaluationResult

FailureKind = Literal["error", "refusal", "malformed"]

# A company whose models the app can call
type Provider = Literal["anthropic", "openai", "google"]

PROVIDERS: tuple[Provider, ...] = ("anthropic", "openai", "google")


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

    async def write_cover_letter(self, prompt: CoverLetterPrompt) -> Outcome[CoverLetterResult]:
        """Write a Cover Letter draft for one Job Posting, as laid out in `prompt`."""
        ...


# An `Llm` calling the Provider with the given API key
type Connect = Callable[[Provider, str], Llm]


@dataclass(frozen=True)
class KeyRefused:
    """Why a Provider would not list its models for an API key, in its own words."""

    reason: str


@dataclass(frozen=True)
class ListedModel:
    """A model a Provider lists for a key that the app can use: a text model, kept by that
    Provider's filtering rules."""

    provider: Provider
    id: str
    display_name: str
    # A dated or versioned name, pinned to one release, rather than a moving name such as
    # `gpt-5` that follows the family's latest
    snapshot: bool
    # The effort levels it accepts, in the Provider's own names; none without an effort control
    efforts: tuple[str, ...]


class ModelLister(Protocol):
    @property
    def available(self) -> tuple[Provider, ...]:
        """The Providers with an adapter: only these can be set up."""
        ...

    async def list_models(self, provider: Provider, api_key: str) -> list[ListedModel] | KeyRefused:
        """The models the Provider lists for the key that the app can use; or why it
        refused the key."""
        ...
