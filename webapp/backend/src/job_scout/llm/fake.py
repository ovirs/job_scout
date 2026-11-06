"""The fake LLM for tests: canned results or failures per step, and a record of the inputs."""

from collections.abc import Awaitable, Callable

from job_scout.clippings.extraction import ManualEntryExtraction
from job_scout.config import Settings
from job_scout.cover_letters.prompt import CoverLetterPrompt, CoverLetterResult
from job_scout.evaluations.prompt import EvaluationPrompt, EvaluationResult
from job_scout.llm.interface import Failure, Outcome
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
    """Reports the models configured in `settings`, as the real adapter would."""

    def __init__(self, settings: Settings) -> None:
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

    async def extract_manual_entry(self, pasted_text: str) -> Outcome[ManualEntryExtraction]:
        return await self.manual_entry_extraction(pasted_text)

    async def evaluate(self, prompt: EvaluationPrompt) -> Outcome[EvaluationResult]:
        return await self.evaluation(prompt)

    async def write_cover_letter(self, prompt: CoverLetterPrompt) -> Outcome[CoverLetterResult]:
        return await self.cover_letter(prompt)
