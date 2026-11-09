"""The fakes for tests: the LLM, with canned results or failures per step and a record of
the inputs, and the model lister, with canned listings that can refuse a key."""

from collections.abc import Awaitable, Callable

from job_scout.clippings.extraction import ManualEntryExtraction
from job_scout.cover_letters.prompt import CoverLetterPrompt, CoverLetterResult
from job_scout.evaluations.prompt import EvaluationPrompt, EvaluationResult
from job_scout.llm.interface import (
    Failure,
    KeyRefused,
    ListedModel,
    ModelChoice,
    Outcome,
    Provider,
)
from job_scout.llm.providers import ADAPTERS
from job_scout.prompts import COVER_LETTER, EVALUATION, MANUAL_ENTRY_EXTRACTION, Prompt


class FakeStep[I, T]:
    """One step of the fake LLM.

    It answers with the responses given to `respond_with`, in order, repeating
    the last one, and records every input it was called with in `calls`. An
    exception given as a response is raised, as an unexpected error would be.
    A hook given to `while_answering` runs during each call, before it answers, as
    the user acting while the LLM works would. It reports the Provider and model of
    the choice it was called with, as answering them.
    """

    def __init__(self, *, default: T, prompt: Prompt) -> None:
        self.calls: list[I] = []
        self._responses: list[T | Failure | Exception] = [default]
        self._prompt = prompt
        self._while_answering: Callable[[I], Awaitable[None]] | None = None

    def respond_with(self, *responses: T | Failure | Exception) -> None:
        self._responses = list(responses)

    def while_answering(self, hook: Callable[[I], Awaitable[None]]) -> None:
        self._while_answering = hook

    async def __call__(self, choice: ModelChoice, inputs: I) -> Outcome[T]:
        self.calls.append(inputs)
        if self._while_answering is not None:
            await self._while_answering(inputs)
        result = self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]
        if isinstance(result, Exception):
            raise result
        return Outcome(
            result=result,
            provider=choice.provider,
            model=choice.model,
            prompt_version=self._prompt.version,
        )


NOTHING_FOUND = ManualEntryExtraction(
    title=None,
    company=None,
    location_text=None,
    description_first_line=None,
    description_last_line=None,
    salary_ranges=[],
    seniority=[],
    employment_type=None,
    workplace_type=None,
    location_restriction=None,
    required_technologies=[],
    nice_to_have_technologies=[],
)

# Passes the checks for a posting judged against no Deal Breakers
NO_DEAL_BREAKERS_JUDGED = EvaluationResult(
    deal_breaker_verdicts=[],
    red_flags=[],
    green_flags=[],
    score=5,
    recommendation="maybe",
    summary="A posting judged against no Deal Breakers.",
)

A_LETTER = CoverLetterResult(
    letter="Dear hiring team,\n\nA letter written by the fake LLM.\n\nKind regards",
    unsupported_requirements=[],
)


class FakeLlm:
    """The steps' canned answers, whatever the model choice and key.

    `connect` stands in for connecting to a Provider: it answers with these steps,
    reporting the choice's Provider and model as the real adapter would, and records
    each choice and key in `connections`.
    """

    def __init__(self) -> None:
        self.connections: list[tuple[ModelChoice, str]] = []
        self.manual_entry_extraction = FakeStep[str, ManualEntryExtraction](
            default=NOTHING_FOUND, prompt=MANUAL_ENTRY_EXTRACTION
        )
        self.evaluation = FakeStep[EvaluationPrompt, EvaluationResult](
            default=NO_DEAL_BREAKERS_JUDGED, prompt=EVALUATION
        )
        self.cover_letter = FakeStep[CoverLetterPrompt, CoverLetterResult](
            default=A_LETTER, prompt=COVER_LETTER
        )

    def connect(self, choice: ModelChoice, api_key: str) -> "FakeConnection":
        self.connections.append((choice, api_key))
        return FakeConnection(self, choice)


class FakeConnection:
    """The fake LLM, connected to one model choice."""

    def __init__(self, llm: FakeLlm, choice: ModelChoice) -> None:
        self._llm = llm
        self._choice = choice

    async def extract_manual_entry(self, pasted_text: str) -> Outcome[ManualEntryExtraction]:
        return await self._llm.manual_entry_extraction(self._choice, pasted_text)

    async def evaluate(self, prompt: EvaluationPrompt) -> Outcome[EvaluationResult]:
        return await self._llm.evaluation(self._choice, prompt)

    async def write_cover_letter(self, prompt: CoverLetterPrompt) -> Outcome[CoverLetterResult]:
        return await self._llm.cover_letter(self._choice, prompt)


OPUS = ListedModel(
    provider="anthropic",
    id="claude-opus-5-5",
    display_name="Claude Opus 5.5",
    snapshot=False,
    efforts=("low", "medium", "high", "xhigh", "max"),
)


class FakeModelLister:
    """Lists each Provider's models in `listings` for any key, as already filtered, and
    records each Provider and key it was asked about in `calls`; after `refuse`, refuses
    every key with the reason. The Providers available are the app's own."""

    available: tuple[Provider, ...] = tuple(ADAPTERS)

    def __init__(self) -> None:
        self.listings: dict[Provider, list[ListedModel]] = {"anthropic": [OPUS]}
        self.calls: list[tuple[Provider, str]] = []
        self._refusal: KeyRefused | None = None

    def refuse(self, reason: str) -> None:
        self._refusal = KeyRefused(reason)

    async def list_models(self, provider: Provider, api_key: str) -> list[ListedModel] | KeyRefused:
        self.calls.append((provider, api_key))
        return self._refusal or list(self.listings.get(provider, []))
