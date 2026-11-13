"""The OpenAI adapter: OpenAI's Responses API through the `openai` SDK, with structured
output in strict mode, called with the run's model choice and its owner's key. The listing
of OpenAI's models is next to it, in `openai_models`, and the step schemas in OpenAI's
dialect in `openai_schema`.

Prompt caching is automatic on OpenAI: the parts that change rarely are sent first, so
calls share the longest prefix, and each owner's calls for a step carry the same
`prompt_cache_key`, so they reach the same cache. Responses are not stored with OpenAI.
Tested against canned HTTP answers; prompt quality is judged by reading results.
"""

import uuid
from typing import Any, cast

import httpx2
import openai
from openai.types.responses import Response
from pydantic import BaseModel, ValidationError

from job_scout.clippings.extraction import ManualEntryExtraction
from job_scout.cover_letters.prompt import CoverLetterPrompt, CoverLetterResult
from job_scout.evaluations.prompt import EvaluationPrompt, EvaluationResult
from job_scout.llm import openai_client, openai_schema
from job_scout.llm.interface import Failure, ModelChoice, Outcome, Step
from job_scout.llm.openai_models import EFFORTS
from job_scout.prompts import COVER_LETTER, EVALUATION, MANUAL_ENTRY_EXTRACTION, Prompt

# The client errors a retry may fix, reported as `error` for the queue to retry: the
# request timed out, or the rate limit was hit. Any other client error is a request OpenAI
# refuses as invalid (an effort the model does not take, an unknown model, a bad key, a
# schema it cannot take), which no retry fixes
TRANSIENT_CLIENT_ERRORS = frozenset({408, 429})


class OpenAiLlm:
    def __init__(
        self,
        choice: ModelChoice,
        api_key: str,
        owner_id: uuid.UUID,
        *,
        http: httpx2.AsyncClient | None = None,
    ) -> None:
        """`owner_id` names the cache the calls share; `http` replaces the SDK's own HTTP
        client, as in tests."""
        self._choice = choice
        self._api_key = api_key
        self._owner_id = owner_id
        self._http = http

    async def extract_manual_entry(self, pasted_text: str) -> Outcome[ManualEntryExtraction]:
        # For a manual entry the user part is the pasted text and nothing else
        return await self._complete(
            step="extraction",
            prompt=MANUAL_ENTRY_EXTRACTION,
            parts=[pasted_text],
            schema=ManualEntryExtraction,
        )

    async def evaluate(self, prompt: EvaluationPrompt) -> Outcome[EvaluationResult]:
        # The user inputs, which change rarely, come before the posting
        return await self._complete(
            step="evaluation", prompt=EVALUATION, parts=prompt.blocks, schema=EvaluationResult
        )

    async def write_cover_letter(self, prompt: CoverLetterPrompt) -> Outcome[CoverLetterResult]:
        # The Career Profile and Writing Guide, which change rarely, come before the request
        return await self._complete(
            step="cover_letter", prompt=COVER_LETTER, parts=prompt.blocks, schema=CoverLetterResult
        )

    async def _complete[T: BaseModel](
        self, *, step: Step, prompt: Prompt, parts: list[str], schema: type[T]
    ) -> Outcome[T]:
        """The call's outcome, with the model OpenAI reports back, or the one asked for when
        it did not answer."""
        effort = self._choice.effort
        if effort is not None and effort not in EFFORTS:
            # The SDK would send it on regardless
            reason = f"OpenAI has no reasoning effort {effort!r}"
            return self._outcome(Failure("rejected", reason), self._choice.model, prompt)
        try:
            strict = openai_schema.convert(schema)
        except openai_schema.UnsupportedSchema as error:
            # Refused before any call, so no retry fixes it
            reason = f"OpenAI cannot take the step's schema: {error}"
            return self._outcome(Failure("rejected", reason), self._choice.model, prompt)
        try:
            # A client per call, closed after it: the worker connects afresh on every attempt
            async with openai_client.client(self._api_key, self._http) as client:
                response = await client.responses.create(
                    model=self._choice.model,
                    instructions=prompt.text,
                    input=[
                        {
                            "role": "user",
                            "content": [{"type": "input_text", "text": part} for part in parts],
                        }
                    ],
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": schema.__name__,
                            "schema": strict,
                            "strict": True,
                        }
                    },
                    # In OpenAI's own names; a level the model does not take is rejected
                    reasoning={"effort": cast(Any, effort)} if effort is not None else openai.omit,
                    prompt_cache_key=f"{self._owner_id}:{step}",
                    store=False,
                )
        except openai.APIStatusError as error:
            transient = error.status_code in TRANSIENT_CLIENT_ERRORS or error.status_code >= 500
            if transient:
                reason = f"The OpenAI API call failed: {openai_client.message(error)}"
                return self._outcome(Failure("error", reason), self._choice.model, prompt)
            reason = f"OpenAI rejected the request: {openai_client.message(error)}"
            return self._outcome(Failure("rejected", reason), self._choice.model, prompt)
        except openai.APIConnectionError as error:
            # No answer at all: a timeout or a dropped connection
            reason = f"The OpenAI API call failed: {error!r}"
            return self._outcome(Failure("error", reason), self._choice.model, prompt)
        return self._outcome(_result(response, schema), response.model, prompt)

    def _outcome[T](self, result: T | Failure, model: str, prompt: Prompt) -> Outcome[T]:
        return Outcome(result=result, provider="openai", model=model, prompt_version=prompt.version)


def _result[T: BaseModel](response: Response, schema: type[T]) -> T | Failure:
    if response.status == "failed":
        message = response.error.message if response.error else "no reason given"
        return Failure("error", f"The OpenAI API call failed: {message}")
    refusals = [
        content.refusal
        for item in response.output
        if item.type == "message"
        for content in item.content
        if content.type == "refusal"
    ]
    if refusals:
        return Failure("refusal", f"The model declined to answer: {' '.join(refusals)}")
    if response.status == "incomplete":
        reason = response.incomplete_details.reason if response.incomplete_details else None
        if reason == "content_filter":
            return Failure("refusal", "The model declined to answer")
        if reason == "max_output_tokens":
            return Failure("malformed", "The answer was cut off at the model's output limit")
        return Failure("malformed", f"The answer stopped early: {reason}")
    try:
        return schema.model_validate_json(response.output_text)
    except ValidationError as error:
        return Failure("malformed", f"The answer did not have the expected shape: {error}")
