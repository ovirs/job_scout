"""The OpenAI adapter, against OpenAI's Responses API answering as its API reference shows:
what it asks for, and how each answer or failure becomes a step's outcome. No real key is
used."""

import json
import uuid
from typing import Any

import httpx2
import pytest

from job_scout.cover_letters.prompt import CoverLetterPrompt, CoverLetterResult
from job_scout.evaluations.prompt import EvaluationPrompt
from job_scout.llm.interface import Failure, ModelChoice
from job_scout.llm.openai_adapter import OpenAiLlm

PROMPT = CoverLetterPrompt(user_inputs="My Career Profile", request="Write for this posting")

LETTER = {"letter": "Dear hiring team", "unsupported_requirements": ["Rust"]}

OWNER = uuid.UUID("0f0e0d0c-0b0a-0908-0706-050403020100")


def response(
    *content: dict[str, Any], status: str = "completed", incomplete: str | None = None
) -> dict[str, Any]:
    return {
        "id": "resp_1",
        "object": "response",
        "created_at": 1762000000,
        "status": status,
        "incomplete_details": {"reason": incomplete} if incomplete else None,
        "model": "gpt-5-2025-08-07",
        "output": [
            {"type": "reasoning", "id": "rs_1", "summary": []},
            {
                "type": "message",
                "id": "msg_1",
                "status": status,
                "role": "assistant",
                "content": list(content),
            },
        ],
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
    }


def text(value: str) -> dict[str, Any]:
    return {"type": "output_text", "text": value, "annotations": []}


def error(message: str, kind: str, code: str | None = None) -> dict[str, Any]:
    return {"error": {"message": message, "type": kind, "param": None, "code": code}}


class OpenAi:
    """OpenAI's API, answering every request with one response and recording the bodies."""

    def __init__(self, status: int, body: Any) -> None:
        self.requests: list[dict[str, Any]] = []
        self._status = status
        self._body = body

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(json.loads(request.content))
        return httpx2.Response(self._status, json=self._body)


def connected(openai: Any, effort: str | None = "low") -> OpenAiLlm:
    return OpenAiLlm(
        ModelChoice(provider="openai", model="gpt-5", effort=effort),
        "a-key",
        OWNER,
        http=httpx2.AsyncClient(transport=httpx2.MockTransport(openai)),
    )


async def write_letter(openai: Any, effort: str | None = "low") -> Any:
    return await connected(openai, effort).write_cover_letter(PROMPT)


async def test_an_answer_is_checked_and_reported_with_the_model_openai_names() -> None:
    outcome = await write_letter(OpenAi(200, response(text(json.dumps(LETTER)))))

    assert outcome.result == CoverLetterResult.model_validate(LETTER)
    assert (outcome.provider, outcome.model) == ("openai", "gpt-5-2025-08-07")


async def test_the_request_carries_the_effort_the_strict_schema_and_a_cache_key() -> None:
    openai = OpenAi(200, response(text(json.dumps(LETTER))))

    await write_letter(openai, effort="low")

    [request] = openai.requests
    assert request["model"] == "gpt-5"
    assert request["reasoning"] == {"effort": "low"}
    schema_format = request["text"]["format"]
    assert (schema_format["type"], schema_format["name"], schema_format["strict"]) == (
        "json_schema",
        "CoverLetterResult",
        True,
    )
    assert schema_format["schema"]["additionalProperties"] is False
    # One key per owner and step, so the owner's calls for a step share OpenAI's cache
    assert request["prompt_cache_key"] == f"{OWNER}:cover_letter"
    assert request["store"] is False
    # What changes rarely comes first, so calls share the longest cached prefix
    assert request["input"] == [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "My Career Profile"},
                {"type": "input_text", "text": "Write for this posting"},
            ],
        }
    ]


async def test_each_step_has_its_own_cache_key() -> None:
    openai = OpenAi(200, response(text("{}")))

    await connected(openai).evaluate(EvaluationPrompt(user_inputs="Inputs", posting="Posting"))
    await connected(openai).extract_manual_entry("Pasted text")

    assert [request["prompt_cache_key"] for request in openai.requests] == [
        f"{OWNER}:evaluation",
        f"{OWNER}:extraction",
    ]


async def test_no_reasoning_is_sent_for_the_providers_default_effort() -> None:
    openai = OpenAi(200, response(text(json.dumps(LETTER))))

    await write_letter(openai, effort=None)

    [request] = openai.requests
    assert "reasoning" not in request


UNSUPPORTED_EFFORT = (
    "Unsupported value: 'reasoning.effort' does not support 'none' with this model."
)


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        pytest.param(
            400,
            error(UNSUPPORTED_EFFORT, "invalid_request_error", "unsupported_value"),
            Failure("rejected", f"OpenAI rejected the request: {UNSUPPORTED_EFFORT}"),
            id="an effort the model does not take",
        ),
        pytest.param(
            404,
            error("The model `gpt-9` does not exist.", "invalid_request_error", "model_not_found"),
            Failure("rejected", "OpenAI rejected the request: The model `gpt-9` does not exist."),
            id="an unknown model",
        ),
        pytest.param(
            401,
            error("Incorrect API key provided.", "invalid_request_error", "invalid_api_key"),
            Failure("rejected", "OpenAI rejected the request: Incorrect API key provided."),
            id="a bad key",
        ),
        pytest.param(
            429,
            error("Rate limit reached for gpt-5.", "requests", "rate_limit_exceeded"),
            Failure("error", "The OpenAI API call failed: Rate limit reached for gpt-5."),
            id="the rate limit",
        ),
        pytest.param(
            500,
            error("The server had an error.", "server_error"),
            Failure("error", "The OpenAI API call failed: The server had an error."),
            id="a server error",
        ),
        pytest.param(
            200,
            response({"type": "refusal", "refusal": "I can't help with that."}),
            Failure("refusal", "The model declined to answer: I can't help with that."),
            id="a refusal",
        ),
        pytest.param(
            200,
            response(status="incomplete", incomplete="content_filter"),
            Failure("refusal", "The model declined to answer"),
            id="an answer withheld by the content filter",
        ),
        pytest.param(
            200,
            response(text('{"letter": "Dear'), status="incomplete", incomplete="max_output_tokens"),
            Failure("malformed", "The answer was cut off at the model's output limit"),
            id="an answer cut off",
        ),
        pytest.param(
            200,
            {
                **response(),
                "status": "failed",
                "error": {"code": "server_error", "message": "Oops"},
            },
            Failure("error", "The OpenAI API call failed: Oops"),
            id="a response that failed",
        ),
    ],
)
async def test_each_failure_becomes_its_kind(status: int, body: Any, expected: Failure) -> None:
    outcome = await write_letter(OpenAi(status, body))

    assert outcome.result == expected
    assert outcome.provider == "openai"


async def test_an_answer_without_the_steps_shape_is_malformed() -> None:
    outcome = await write_letter(OpenAi(200, response(text('{"letter": "Dear hiring team"}'))))

    assert isinstance(outcome.result, Failure)
    assert outcome.result.kind == "malformed"


async def test_a_timeout_is_an_error_to_retry() -> None:
    def timing_out(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("timed out", request=request)

    outcome = await write_letter(timing_out)

    assert isinstance(outcome.result, Failure)
    assert outcome.result.kind == "error"


async def test_an_effort_openai_does_not_name_is_rejected_without_a_call() -> None:
    openai = OpenAi(200, response(text(json.dumps(LETTER))))

    outcome = await write_letter(openai, effort="extreme")

    assert outcome.result == Failure("rejected", "OpenAI has no reasoning effort 'extreme'")
    assert openai.requests == []
