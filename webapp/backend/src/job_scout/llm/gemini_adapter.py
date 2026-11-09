"""The Gemini adapter: Google's Gemini API through the `google-genai` SDK, with structured
output, called with the run's model choice and its owner's key. The listing of Gemini's
models is next to it, in `gemini_models`, and the step schemas in Gemini's dialect in
`gemini_schema`.

Prompt caching is implicit on Gemini: the parts that change rarely are sent first, so
calls share the longest prefix. Tested against canned HTTP answers; prompt quality is
judged by reading results.
"""

import httpx2
from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from job_scout.clippings.extraction import ManualEntryExtraction
from job_scout.cover_letters.prompt import CoverLetterPrompt, CoverLetterResult
from job_scout.evaluations.prompt import EvaluationPrompt, EvaluationResult
from job_scout.llm import gemini_schema
from job_scout.llm.gemini_client import TRANSPORT_ERRORS, http_options
from job_scout.llm.gemini_models import EFFORTS
from job_scout.llm.interface import Failure, ModelChoice, Outcome
from job_scout.prompts import COVER_LETTER, EVALUATION, MANUAL_ENTRY_EXTRACTION, Prompt

# The client errors a retry may fix, reported as `error` for the queue to retry: the
# request timed out, or the rate limit was hit. Any other client error is a request Google
# refuses as invalid (an effort the model does not take, an unknown model, a bad key, a
# schema it cannot take), which no retry fixes
TRANSIENT_CLIENT_ERRORS = frozenset({408, 429})

# The finish reasons for an answer the model withheld as unsafe or prohibited
REFUSALS = frozenset(
    {
        types.FinishReason.SAFETY,
        types.FinishReason.PROHIBITED_CONTENT,
        types.FinishReason.BLOCKLIST,
        types.FinishReason.SPII,
    }
)


class GeminiLlm:
    def __init__(
        self, choice: ModelChoice, api_key: str, *, http: httpx2.AsyncClient | None = None
    ) -> None:
        """`http` replaces the SDK's own HTTP client, as in tests."""
        self._choice = choice
        self._api_key = api_key
        self._http = http

    async def extract_manual_entry(self, pasted_text: str) -> Outcome[ManualEntryExtraction]:
        # For a manual entry the user part is the pasted text and nothing else
        return await self._complete(
            prompt=MANUAL_ENTRY_EXTRACTION, parts=[pasted_text], schema=ManualEntryExtraction
        )

    async def evaluate(self, prompt: EvaluationPrompt) -> Outcome[EvaluationResult]:
        # The user inputs, which change rarely, come before the posting
        return await self._complete(prompt=EVALUATION, parts=prompt.blocks, schema=EvaluationResult)

    async def write_cover_letter(self, prompt: CoverLetterPrompt) -> Outcome[CoverLetterResult]:
        # The Career Profile and Writing Guide, which change rarely, come before the request
        return await self._complete(
            prompt=COVER_LETTER, parts=prompt.blocks, schema=CoverLetterResult
        )

    async def _complete[T: BaseModel](
        self, *, prompt: Prompt, parts: list[str], schema: type[T]
    ) -> Outcome[T]:
        """The call's outcome, with the model Google reports back, or the one asked for when
        it did not answer."""
        effort = self._choice.effort
        if effort is not None and effort not in EFFORTS:
            # The SDK would send it on regardless
            reason = f"Gemini has no thinking level {effort!r}"
            return self._outcome(Failure("rejected", reason), self._choice.model, prompt)
        try:
            config = _config(prompt, schema, effort)
        except gemini_schema.UnsupportedSchema as error:
            reason = f"Gemini cannot take the step's schema: {error}"
            return self._outcome(Failure("malformed", reason), self._choice.model, prompt)
        try:
            # A client per call, closed after it: the worker connects afresh on every attempt
            async with genai.Client(
                api_key=self._api_key, http_options=http_options(self._http)
            ).aio as client:
                response = await client.models.generate_content(
                    model=self._choice.model,
                    contents=types.Content(
                        role="user", parts=[types.Part(text=part) for part in parts]
                    ),
                    config=config,
                )
        except genai.errors.ClientError as error:
            if error.code in TRANSIENT_CLIENT_ERRORS:
                reason = f"The Gemini API call failed: {error.message or error}"
                return self._outcome(Failure("error", reason), self._choice.model, prompt)
            reason = f"Google rejected the request: {error.message or error}"
            return self._outcome(Failure("rejected", reason), self._choice.model, prompt)
        except genai.errors.APIError as error:
            reason = f"The Gemini API call failed: {error.message or error}"
            return self._outcome(Failure("error", reason), self._choice.model, prompt)
        except TRANSPORT_ERRORS as error:
            reason = f"The Gemini API call failed: {error!r}"
            return self._outcome(Failure("error", reason), self._choice.model, prompt)
        model = response.model_version or self._choice.model
        return self._outcome(_result(response, schema), model, prompt)

    def _outcome[T](self, result: T | Failure, model: str, prompt: Prompt) -> Outcome[T]:
        return Outcome(result=result, provider="google", model=model, prompt_version=prompt.version)


def _config(
    prompt: Prompt, schema: type[BaseModel], effort: str | None
) -> types.GenerateContentConfig:
    """The call's configuration, with the effort as the thinking level, in Gemini's own
    names: a level the model does not take is rejected by Google. Raises
    `UnsupportedSchema`."""
    thinking = None
    if effort is not None:
        thinking = types.ThinkingConfig(thinking_level=types.ThinkingLevel(effort.upper()))
    return types.GenerateContentConfig(
        system_instruction=prompt.text,
        response_mime_type="application/json",
        response_json_schema=gemini_schema.convert(schema),
        thinking_config=thinking,
    )


def _result[T: BaseModel](response: types.GenerateContentResponse, schema: type[T]) -> T | Failure:
    if response.prompt_feedback is not None and response.prompt_feedback.block_reason:
        return Failure("refusal", "The model declined to answer")
    if not response.candidates:
        return Failure("malformed", "The answer had no content")
    finish_reason = response.candidates[0].finish_reason
    if finish_reason in REFUSALS:
        return Failure("refusal", "The model declined to answer")
    if finish_reason == types.FinishReason.MAX_TOKENS:
        return Failure("malformed", "The answer was cut off at the model's output limit")
    if finish_reason not in (types.FinishReason.STOP, None):
        return Failure("malformed", f"The answer stopped early: {finish_reason}")
    try:
        return schema.model_validate_json(response.text or "")
    except ValidationError as error:
        return Failure("malformed", f"The answer did not have the expected shape: {error}")
