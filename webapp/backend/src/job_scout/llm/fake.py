"""The fakes for tests: the LLM, with canned results or failures per step and a record of
the inputs, and the model lister, with canned listings that can refuse a key."""

from collections.abc import Awaitable, Callable

from job_scout.clippings.extraction import ManualEntryExtraction
from job_scout.config import Settings
from job_scout.cover_letters.prompt import CoverLetterPrompt, CoverLetterResult
from job_scout.evaluations.prompt import EvaluationPrompt, EvaluationResult
from job_scout.llm.interface import Failure, KeyRefused, Outcome, Provider
from job_scout.llm.providers import ADAPTERS
from job_scout.prompts import COVER_LETTER, EVALUATION, MANUAL_ENTRY_EXTRACTION, Prompt


class FakeStep[I, T]:
    """One step of the fake LLM.

    It answers with the responses given to `respond_with`, in order, repeating
    the last one, and records every input it was called with in `calls`. An
    exception given as a response is raised, as an unexpected error would be.
    A hook given to `while_answering` runs during each call, before it answers, as
    the user acting while the LLM works would.
    """

    def __init__(self, *, default: T, model: str, prompt: Prompt) -> None:
        self.calls: list[I] = []
        self._responses: list[T | Failure | Exception] = [default]
        self._model = model
        self._prompt = prompt
        self._while_answering: Callable[[I], Awaitable[None]] | None = None

    def respond_with(self, *responses: T | Failure | Exception) -> None:
        self._responses = list(responses)

    def while_answering(self, hook: Callable[[I], Awaitable[None]]) -> None:
        self._while_answering = hook

    async def __call__(self, inputs: I) -> Outcome[T]:
        self.calls.append(inputs)
        if self._while_answering is not None:
            await self._while_answering(inputs)
        result = self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]
        if isinstance(result, Exception):
            raise result
        return Outcome(result=result, model=self._model, prompt_version=self._prompt.version)


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
    """Reports the models configured in `settings`, as the real adapter would.

    `connect` stands in for connecting to a Provider: it answers with this one fake,
    whatever the Provider and key, and records each in `connections`.
    """

    def __init__(self, settings: Settings) -> None:
        self.connections: list[tuple[Provider, str]] = []
        self.manual_entry_extraction = FakeStep[str, ManualEntryExtraction](
            default=NOTHING_FOUND,
            model=settings.extraction_model,
            prompt=MANUAL_ENTRY_EXTRACTION,
        )
        self.evaluation = FakeStep[EvaluationPrompt, EvaluationResult](
            default=NO_DEAL_BREAKERS_JUDGED,
            model=settings.evaluation_model,
            prompt=EVALUATION,
        )
        self.cover_letter = FakeStep[CoverLetterPrompt, CoverLetterResult](
            default=A_LETTER,
            model=settings.cover_letter_model,
            prompt=COVER_LETTER,
        )

    def connect(self, provider: Provider, api_key: str) -> "FakeLlm":
        self.connections.append((provider, api_key))
        return self

    async def extract_manual_entry(self, pasted_text: str) -> Outcome[ManualEntryExtraction]:
        return await self.manual_entry_extraction(pasted_text)

    async def evaluate(self, prompt: EvaluationPrompt) -> Outcome[EvaluationResult]:
        return await self.evaluation(prompt)

    async def write_cover_letter(self, prompt: CoverLetterPrompt) -> Outcome[CoverLetterResult]:
        return await self.cover_letter(prompt)


class FakeModelLister:
    """Lists `models` for any key, and records each Provider and key it was asked about in
    `calls`; after `refuse`, refuses every key with the reason. The Providers available are
    the app's own."""

    available: tuple[Provider, ...] = tuple(ADAPTERS)

    def __init__(self, models: list[str] | None = None) -> None:
        self.models = models if models is not None else ["claude-opus-5-5"]
        self.calls: list[tuple[Provider, str]] = []
        self._refusal: KeyRefused | None = None

    def refuse(self, reason: str) -> None:
        self._refusal = KeyRefused(reason)

    async def list_models(self, provider: Provider, api_key: str) -> list[str] | KeyRefused:
        self.calls.append((provider, api_key))
        return self._refusal or list(self.models)
