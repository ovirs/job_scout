"""The real LLM adapter: the Anthropic API, with structured output.

Not covered by automated tests; prompt quality is judged by reading results.
"""

import anthropic
from anthropic.types import OutputConfigParam
from pydantic import BaseModel, ValidationError

from job_scout.config import Effort, Settings
from job_scout.extraction import ManualEntryExtraction
from job_scout.llm.interface import Failure, Outcome
from job_scout.prompts import MANUAL_ENTRY_EXTRACTION, Prompt

MAX_TOKENS = 8192


class AnthropicLlm:
    def __init__(self, settings: Settings) -> None:
        secret = settings.anthropic_api_key
        api_key = secret.get_secret_value() if secret else ""  # blank counts as not set
        self._client = anthropic.AsyncAnthropic(api_key=api_key) if api_key else None
        self._extraction_model = settings.extraction_model
        self._extraction_effort = settings.extraction_effort

    async def extract_manual_entry(self, pasted_text: str) -> Outcome[ManualEntryExtraction]:
        # For a manual entry the user block is the pasted text and nothing else
        return await self._complete(
            model=self._extraction_model,
            effort=self._extraction_effort,
            prompt=MANUAL_ENTRY_EXTRACTION,
            content=pasted_text,
            schema=ManualEntryExtraction,
        )

    async def _complete[T: BaseModel](
        self, *, model: str, effort: Effort | None, prompt: Prompt, content: str, schema: type[T]
    ) -> Outcome[T]:
        result = await self._call(
            model=model, effort=effort, prompt=prompt, content=content, schema=schema
        )
        return Outcome(result=result, model=model, prompt_version=prompt.version)

    async def _call[T: BaseModel](
        self, *, model: str, effort: Effort | None, prompt: Prompt, content: str, schema: type[T]
    ) -> T | Failure:
        if self._client is None:
            return Failure("error", "ANTHROPIC_API_KEY is not set")
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
