"""The real LLM adapter: the Anthropic API, with structured output, called with the run's
model choice and its owner's key. The listing of Anthropic's models is next to it, in
`anthropic_models`.

Not covered by automated tests; prompt quality is judged by reading results.
"""

import uuid
from typing import Any, cast

import anthropic
from anthropic.types import OutputConfigParam, TextBlockParam
from pydantic import BaseModel, ValidationError

from job_scout.clippings.extraction import ManualEntryExtraction
from job_scout.cover_letters.prompt import CoverLetterPrompt, CoverLetterResult
from job_scout.evaluations.prompt import EvaluationPrompt, EvaluationResult
from job_scout.llm.interface import Failure, ModelChoice, Outcome
from job_scout.prompts import COVER_LETTER, EVALUATION, MANUAL_ENTRY_EXTRACTION, Prompt

MAX_TOKENS = 8192

# A user message: plain text, or blocks of text sent in order
type Content = str | list[TextBlockParam]

# The errors for a request Anthropic refuses as invalid, which a retry would not fix: a bad
# request (an effort the model does not take, say), a bad key, a key without access, or an
# unknown model
REJECTED = (
    anthropic.BadRequestError,  # 400
    anthropic.AuthenticationError,  # 401
    anthropic.PermissionDeniedError,  # 403
    anthropic.NotFoundError,  # 404
)


class AnthropicLlm:
    def __init__(self, choice: ModelChoice, api_key: str, owner_id: uuid.UUID) -> None:
        """`owner_id` is unused: Anthropic's cache needs no key."""
        self._choice = choice
        self._api_key = api_key

    async def extract_manual_entry(self, pasted_text: str) -> Outcome[ManualEntryExtraction]:
        # For a manual entry the user block is the pasted text and nothing else
        return await self._complete(
            prompt=MANUAL_ENTRY_EXTRACTION, content=pasted_text, schema=ManualEntryExtraction
        )

    async def evaluate(self, prompt: EvaluationPrompt) -> Outcome[EvaluationResult]:
        # The user inputs change rarely, so the instructions and they are cached together;
        # the posting comes last
        content: list[TextBlockParam] = [
            {"type": "text", "text": prompt.user_inputs, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": prompt.posting},
        ]
        return await self._complete(prompt=EVALUATION, content=content, schema=EvaluationResult)

    async def write_cover_letter(self, prompt: CoverLetterPrompt) -> Outcome[CoverLetterResult]:
        # The Career Profile and Writing Guide change rarely, so they are cached with the
        # instructions; the posting, flags and the letter's own instruction come after
        content: list[TextBlockParam] = [
            {"type": "text", "text": prompt.user_inputs, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": prompt.request},
        ]
        return await self._complete(prompt=COVER_LETTER, content=content, schema=CoverLetterResult)

    async def _complete[T: BaseModel](
        self, *, prompt: Prompt, content: Content, schema: type[T]
    ) -> Outcome[T]:
        """The call's outcome, with the model Anthropic reports back, or the one asked for
        when it did not answer."""
        output_config: OutputConfigParam = {
            "format": {"type": "json_schema", "schema": anthropic.transform_schema(schema)}
        }
        if self._choice.effort is not None:
            # Stored in Anthropic's own names; a level the model does not take is rejected
            output_config["effort"] = cast(Any, self._choice.effort)
        try:
            # A client per call, closed after it: the worker connects afresh on every attempt
            async with anthropic.AsyncAnthropic(api_key=self._api_key) as client:
                response = await client.messages.create(
                    model=self._choice.model,
                    max_tokens=MAX_TOKENS,
                    system=prompt.text,
                    messages=[{"role": "user", "content": content}],
                    output_config=output_config,
                )
        except REJECTED as error:
            reason = f"Anthropic rejected the request: {error}"
            return self._outcome(Failure("rejected", reason), self._choice.model, prompt)
        except anthropic.APIError as error:
            reason = f"The Anthropic API call failed: {error}"
            return self._outcome(Failure("error", reason), self._choice.model, prompt)
        return self._outcome(_result(response, schema), response.model, prompt)

    def _outcome[T](self, result: T | Failure, model: str, prompt: Prompt) -> Outcome[T]:
        return Outcome(
            result=result, provider="anthropic", model=model, prompt_version=prompt.version
        )


def _result[T: BaseModel](response: anthropic.types.Message, schema: type[T]) -> T | Failure:
    if response.stop_reason == "refusal":
        return Failure("refusal", "The model declined to answer")
    if response.stop_reason == "max_tokens":
        return Failure("malformed", f"The answer was cut off at {MAX_TOKENS} tokens")
    text = "".join(block.text for block in response.content if block.type == "text")
    try:
        return schema.model_validate_json(text)
    except ValidationError as error:
        return Failure("malformed", f"The answer did not have the expected shape: {error}")
