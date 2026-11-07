"""The real LLM adapter: the Anthropic API, with structured output.

Not covered by automated tests; prompt quality is judged by reading results.
"""

import anthropic
from anthropic.types import OutputConfigParam, TextBlockParam
from pydantic import BaseModel, ValidationError

from job_scout.clippings.extraction import ManualEntryExtraction
from job_scout.config import Effort, Settings
from job_scout.cover_letters.prompt import CoverLetterPrompt, CoverLetterResult
from job_scout.evaluations.prompt import EvaluationPrompt, EvaluationResult
from job_scout.llm.interface import Failure, Outcome
from job_scout.prompts import COVER_LETTER, EVALUATION, MANUAL_ENTRY_EXTRACTION, Prompt
from job_scout.settings.domain import ListingRefused
from job_scout.settings.models import Provider

MAX_TOKENS = 8192

# A user message: plain text, or blocks of text sent in order
type Content = str | list[TextBlockParam]


class AnthropicModelLister:
    """Checks a key by listing the Provider's models with the official SDK."""

    async def list_models(self, provider: Provider, api_key: str) -> list[str]:
        if provider != "anthropic":
            raise ListingRefused(f"{provider} is not available yet")
        client = anthropic.AsyncAnthropic(api_key=api_key)
        try:
            return [model.id async for model in client.models.list(limit=1000)]
        except anthropic.APIError as error:
            raise ListingRefused(error.message) from error
        finally:
            await client.close()


class AnthropicLlm:
    def __init__(self, settings: Settings, api_key: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._extraction_model = settings.extraction_model
        self._extraction_effort = settings.extraction_effort
        self._evaluation_model = settings.evaluation_model
        self._evaluation_effort = settings.evaluation_effort
        self._cover_letter_model = settings.cover_letter_model
        self._cover_letter_effort = settings.cover_letter_effort

    async def extract_manual_entry(self, pasted_text: str) -> Outcome[ManualEntryExtraction]:
        # For a manual entry the user block is the pasted text and nothing else
        return await self._complete(
            model=self._extraction_model,
            effort=self._extraction_effort,
            prompt=MANUAL_ENTRY_EXTRACTION,
            content=pasted_text,
            schema=ManualEntryExtraction,
        )

    async def evaluate(self, prompt: EvaluationPrompt) -> Outcome[EvaluationResult]:
        # The user inputs change rarely, so the instructions and they are cached together;
        # the posting comes last
        content: list[TextBlockParam] = [
            {"type": "text", "text": prompt.user_inputs, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": prompt.posting},
        ]
        return await self._complete(
            model=self._evaluation_model,
            effort=self._evaluation_effort,
            prompt=EVALUATION,
            content=content,
            schema=EvaluationResult,
        )

    async def write_cover_letter(self, prompt: CoverLetterPrompt) -> Outcome[CoverLetterResult]:
        # The Career Profile and Writing Guide change rarely, so they are cached with the
        # instructions; the posting, flags and the letter's own instruction come after
        content: list[TextBlockParam] = [
            {"type": "text", "text": prompt.user_inputs, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": prompt.request},
        ]
        return await self._complete(
            model=self._cover_letter_model,
            effort=self._cover_letter_effort,
            prompt=COVER_LETTER,
            content=content,
            schema=CoverLetterResult,
        )

    async def _complete[T: BaseModel](
        self,
        *,
        model: str,
        effort: Effort | None,
        prompt: Prompt,
        content: Content,
        schema: type[T],
    ) -> Outcome[T]:
        result = await self._call(
            model=model, effort=effort, prompt=prompt, content=content, schema=schema
        )
        return Outcome(result=result, model=model, prompt_version=prompt.version)

    async def _call[T: BaseModel](
        self,
        *,
        model: str,
        effort: Effort | None,
        prompt: Prompt,
        content: Content,
        schema: type[T],
    ) -> T | Failure:
        output_config: OutputConfigParam = {
            "format": {"type": "json_schema", "schema": anthropic.transform_schema(schema)}
        }
        if effort:
            output_config["effort"] = effort
        try:
            response = await self._client.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                system=prompt.text,
                messages=[{"role": "user", "content": content}],
                output_config=output_config,
            )
        except anthropic.APIError as error:
            return Failure("error", f"The Anthropic API call failed: {error}")
        if response.stop_reason == "refusal":
            return Failure("refusal", "The model declined to answer")
        if response.stop_reason == "max_tokens":
            return Failure("malformed", f"The answer was cut off at {MAX_TOKENS} tokens")
        text = "".join(block.text for block in response.content if block.type == "text")
        try:
            return schema.model_validate_json(text)
        except ValidationError as error:
            return Failure("malformed", f"The answer did not have the expected shape: {error}")
