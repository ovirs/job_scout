"""The Gemini adapter, against Google's API answering as its REST docs show: what it asks
for, and how each answer or failure becomes a step's outcome. No real key is used."""

import json
from typing import Any

import httpx2
import pytest

from job_scout.cover_letters.prompt import CoverLetterPrompt, CoverLetterResult
from job_scout.llm.gemini_adapter import GeminiLlm
from job_scout.llm.interface import Failure, ModelChoice

PROMPT = CoverLetterPrompt(user_inputs="My Career Profile", request="Write for this posting")

LETTER = {"letter": "Dear hiring team", "unsupported_requirements": ["Rust"]}


def answer(text: str, finish_reason: str = "STOP") -> dict[str, Any]:
    return {
        "candidates": [
            {"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": finish_reason}
        ],
        "modelVersion": "gemini-2.5-pro-002",
    }


def error(code: int, status: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "status": status}}


class Google:
    """Google's API, answering every request with one response and recording the bodies."""

    def __init__(self, status: int, body: Any) -> None:
        self.requests: list[dict[str, Any]] = []
        self._status = status
        self._body = body

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(json.loads(request.content))
        return httpx2.Response(self._status, json=self._body)


async def write_letter(google: Any, effort: str | None = "low") -> Any:
    llm = GeminiLlm(
        ModelChoice(provider="google", model="gemini-2.5-pro", effort=effort),
        "a-key",
        http=httpx2.AsyncClient(transport=httpx2.MockTransport(google)),
    )
    return await llm.write_cover_letter(PROMPT)


async def test_an_answer_is_checked_and_reported_with_the_model_google_names() -> None:
    outcome = await write_letter(Google(200, answer(json.dumps(LETTER))))

    assert outcome.result == CoverLetterResult.model_validate(LETTER)
    assert (outcome.provider, outcome.model) == ("google", "gemini-2.5-pro-002")


async def test_the_request_carries_the_effort_as_the_thinking_level_and_the_steps_schema() -> None:
    google = Google(200, answer(json.dumps(LETTER)))

    await write_letter(google, effort="low")

    [request] = google.requests
    config = request["generationConfig"]
    assert config["thinkingConfig"] == {"thinking_level": "LOW"}
    assert config["responseMimeType"] == "application/json"
    assert config["responseJsonSchema"]["required"] == ["letter", "unsupported_requirements"]
    # What changes rarely comes first, for Gemini's implicit caching
    assert request["contents"] == [
        {
            "role": "user",
            "parts": [{"text": "My Career Profile"}, {"text": "Write for this posting"}],
        }
    ]


async def test_no_thinking_level_is_sent_for_the_providers_default_effort() -> None:
    google = Google(200, answer(json.dumps(LETTER)))

    await write_letter(google, effort=None)

    [request] = google.requests
    assert "thinkingConfig" not in request["generationConfig"]


UNSUPPORTED_LEVEL = "Thinking level MINIMAL is not supported for this model."


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        pytest.param(
            400,
            error(400, "INVALID_ARGUMENT", UNSUPPORTED_LEVEL),
            Failure("rejected", f"Google rejected the request: {UNSUPPORTED_LEVEL}"),
            id="an effort the model does not take",
        ),
        pytest.param(
            404,
            error(404, "NOT_FOUND", "models/gemini-9 is not found"),
            Failure("rejected", "Google rejected the request: models/gemini-9 is not found"),
            id="an unknown model",
        ),
        pytest.param(
            429,
            error(429, "RESOURCE_EXHAUSTED", "Quota exceeded"),
            Failure("error", "The Gemini API call failed: Quota exceeded"),
            id="the rate limit",
        ),
        pytest.param(
            503,
            error(503, "UNAVAILABLE", "The model is overloaded"),
            Failure("error", "The Gemini API call failed: The model is overloaded"),
            id="a server error",
        ),
        pytest.param(
            200,
            answer("", finish_reason="SAFETY"),
            Failure("refusal", "The model declined to answer"),
            id="an answer withheld as unsafe",
        ),
        pytest.param(
            200,
            {"promptFeedback": {"blockReason": "PROHIBITED_CONTENT"}},
            Failure("refusal", "The model declined to answer"),
            id="a prompt blocked",
        ),
        pytest.param(
            200,
            answer('{"letter": "Dear', finish_reason="MAX_TOKENS"),
            Failure("malformed", "The answer was cut off at the model's output limit"),
            id="an answer cut off",
        ),
    ],
)
async def test_each_failure_becomes_its_kind(status: int, body: Any, expected: Failure) -> None:
    outcome = await write_letter(Google(status, body))

    assert outcome.result == expected
    assert outcome.provider == "google"


async def test_an_answer_without_the_steps_shape_is_malformed() -> None:
    outcome = await write_letter(Google(200, answer('{"letter": "Dear hiring team"}')))

    assert isinstance(outcome.result, Failure)
    assert outcome.result.kind == "malformed"


async def test_a_timeout_is_an_error_to_retry() -> None:
    def timing_out(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("timed out", request=request)

    outcome = await write_letter(timing_out)

    assert isinstance(outcome.result, Failure)
    assert outcome.result.kind == "error"


async def test_an_effort_that_is_not_a_thinking_level_is_rejected_without_a_call() -> None:
    google = Google(200, answer(json.dumps(LETTER)))

    outcome = await write_letter(google, effort="max")

    assert outcome.result == Failure("rejected", "Gemini has no thinking level 'max'")
    assert google.requests == []
