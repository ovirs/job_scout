"""The fake LLM for tests: canned results or failures per step, and a record of the inputs."""

from job_scout.config import Settings
from job_scout.extraction import ManualEntryExtraction
from job_scout.llm.interface import Failure, Outcome
from job_scout.prompts import MANUAL_ENTRY_EXTRACTION, Prompt


class FakeStep[I, T]:
    """One step of the fake LLM.

    It answers with the responses given to `respond_with`, in order, repeating
    the last one, and records every input it was called with in `calls`. An
    exception given as a response is raised, as an unexpected error would be.
    """

    def __init__(self, *, default: T, model: str, prompt: Prompt) -> None:
        self.calls: list[I] = []
        self._responses: list[T | Failure | Exception] = [default]
        self._model = model
        self._prompt = prompt

    def respond_with(self, *responses: T | Failure | Exception) -> None:
        self._responses = list(responses)

    def __call__(self, inputs: I) -> Outcome[T]:
        self.calls.append(inputs)
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


class FakeLlm:
    """Reports the models configured in `settings`, as the real adapter would."""

    def __init__(self, settings: Settings) -> None:
        self.manual_entry_extraction = FakeStep[str, ManualEntryExtraction](
            default=NOTHING_FOUND,
            model=settings.extraction_model,
            prompt=MANUAL_ENTRY_EXTRACTION,
        )

    async def extract_manual_entry(self, pasted_text: str) -> Outcome[ManualEntryExtraction]:
        return self.manual_entry_extraction(pasted_text)
