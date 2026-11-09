"""The default model choice per LLM step: set in Settings, required by the setup gate, and
taken by every run when it is queued."""

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from clipping_helpers import ENVELOPE, PASTED_TEXT, submit_and_extract
from conftest import TEST_KEY
from test_applications import started_application
from test_cover_letters import cover_letter, generate
from test_evaluations import write_career_profile

from job_scout.llm.fake import FakeLlm
from job_scout.llm.interface import ModelChoice

RunTasks = Callable[[], Awaitable[None]]

OPUS = {"provider": "anthropic", "model": "claude-opus-5-5", "effort": None}
OPUS_HIGH = {**OPUS, "effort": "high"}


async def save_defaults(client: httpx.AsyncClient, **choices: dict[str, Any]) -> httpx.Response:
    return await client.put("/api/settings/defaults", json=choices)


async def defaults(client: httpx.AsyncClient) -> dict[str, dict[str, Any]]:
    response = await client.get("/api/settings/defaults")
    assert response.status_code == 200
    return {entry["step"]: entry for entry in response.json()}


async def test_one_choice_saved_for_every_step_is_each_steps_default(
    client_with_provider_only: httpx.AsyncClient,
) -> None:
    client = client_with_provider_only

    saved = await save_defaults(
        client, extraction=OPUS_HIGH, evaluation=OPUS_HIGH, cover_letter=OPUS_HIGH
    )

    assert saved.status_code == 204
    listed = await defaults(client)
    assert {step: entry["choice"] for step, entry in listed.items()} == {
        "extraction": OPUS_HIGH,
        "evaluation": OPUS_HIGH,
        "cover_letter": OPUS_HIGH,
    }
    assert {entry["problem"] for entry in listed.values()} == {None}


async def test_saving_one_steps_default_leaves_the_others(
    client: httpx.AsyncClient,
) -> None:
    saved = await save_defaults(client, evaluation=OPUS_HIGH)

    assert saved.status_code == 204
    listed = await defaults(client)
    assert {step: entry["choice"] for step, entry in listed.items()} == {
        "extraction": OPUS,
        "evaluation": OPUS_HIGH,
        "cover_letter": OPUS,
    }


async def test_the_app_is_set_up_once_every_step_has_a_default(
    client_with_provider_only: httpx.AsyncClient,
) -> None:
    client = client_with_provider_only
    before = (await client.get("/api/setup")).json()
    listed_before = await defaults(client)
    await save_defaults(client, extraction=OPUS, evaluation=OPUS)
    with_two = (await client.get("/api/setup")).json()

    await save_defaults(client, cover_letter=OPUS)

    assert before == {"has_provider": True, "has_defaults": False}
    assert {entry["choice"] for entry in listed_before.values()} == {None}
    assert with_two == {"has_provider": True, "has_defaults": False}
    assert (await client.get("/api/setup")).json() == {"has_provider": True, "has_defaults": True}


async def test_until_every_step_has_a_default_no_llm_run_starts(
    client_with_provider_only: httpx.AsyncClient,
    queued_tasks: Callable[[], Awaitable[list[str]]],
) -> None:
    client = client_with_provider_only
    await save_defaults(client, extraction=OPUS)

    refused = [
        await client.post("/api/clippings", json={"pasted_text": PASTED_TEXT}),
        await client.post("/api/evaluations/rerun-unacted"),
    ]

    assert [response.status_code for response in refused] == [409, 409]
    assert {response.json()["detail"] for response in refused} == {
        "Choose a default model for every step in Settings"
    }
    assert await queued_tasks() == []


async def test_a_default_whose_model_is_not_offered_is_refused(
    client: httpx.AsyncClient,
) -> None:
    await client.put("/api/settings/hidden-models/anthropic/claude-opus-5-5")

    refused = [
        await save_defaults(client, evaluation={**OPUS, "model": "claude-opus-4-1"}),
        await save_defaults(client, evaluation=OPUS),  # hidden
        await save_defaults(client, evaluation={**OPUS, "provider": "openai"}),
    ]

    assert [response.status_code for response in refused] == [422] * 3
    assert (
        refused[0].json()["detail"] == "Anthropic does not offer claude-opus-4-1, or it is hidden"
    )
    assert (
        refused[1].json()["detail"] == "Anthropic does not offer claude-opus-5-5, or it is hidden"
    )
    assert refused[2].json()["detail"] == "There is no API key for OpenAI"
    assert (await defaults(client))["evaluation"]["choice"] == OPUS


async def test_a_default_with_an_effort_the_model_does_not_take_is_refused_and_nothing_is_saved(
    client: httpx.AsyncClient,
) -> None:
    refused = await save_defaults(
        client, extraction=OPUS_HIGH, evaluation={**OPUS, "effort": "minimal"}
    )

    assert refused.status_code == 422
    assert refused.json()["detail"] == "claude-opus-5-5 does not take the effort minimal"
    assert (await defaults(client))["extraction"]["choice"] == OPUS


async def test_a_default_that_can_no_longer_be_used_is_shown_with_why(
    client: httpx.AsyncClient,
) -> None:
    await client.put("/api/settings/hidden-models/anthropic/claude-opus-5-5")
    hidden = await defaults(client)
    await client.delete("/api/settings/hidden-models/anthropic/claude-opus-5-5")
    await client.delete("/api/settings/providers/anthropic/key")

    without_key = await defaults(client)

    assert hidden["evaluation"]["choice"] == OPUS  # kept, to fix in Settings
    assert hidden["evaluation"]["problem"] == (
        "Anthropic does not offer claude-opus-5-5, or it is hidden"
    )
    assert without_key["evaluation"]["problem"] == "There is no API key for Anthropic"


def a_choice(effort: str | None) -> ModelChoice:
    return ModelChoice(provider="anthropic", model="claude-opus-5-5", effort=effort)


async def test_each_steps_runs_call_that_steps_default(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    await save_defaults(
        client,
        extraction={**OPUS, "effort": "low"},
        evaluation={**OPUS, "effort": "high"},
        cover_letter={**OPUS, "effort": "max"},
    )

    application = await started_application(client, fake_llm, run_queued_tasks)
    await generate(client, application["id"])
    await run_queued_tasks()

    assert fake_llm.connections == [
        (a_choice("low"), TEST_KEY),  # reading the Clipping
        (a_choice("high"), TEST_KEY),  # the Evaluation queued on confirming it
        (a_choice("max"), TEST_KEY),  # the Cover Letter
    ]
    assert (await cover_letter(client, application["id"]))["draft"]["model"] == "claude-opus-5-5"


async def test_a_run_that_starts_on_its_own_with_an_unusable_default_fails_at_once(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    queued_tasks: Callable[[], Awaitable[list[str]]],
) -> None:
    await write_career_profile(client)
    clipping = await submit_and_extract(client, run_queued_tasks)
    await client.put("/api/settings/hidden-models/anthropic/claude-opus-5-5")

    confirmed = await client.post(f"/api/clippings/{clipping['id']}/confirm", json=ENVELOPE)
    submitted = await client.post("/api/clippings", json={"pasted_text": PASTED_TEXT})

    assert confirmed.status_code == submitted.status_code == 201
    assert await queued_tasks() == []  # never retried
    reason = (
        "The default model for this step cannot be used: Anthropic does not offer"
        " claude-opus-5-5, or it is hidden. Choose another in Settings"
    )
    posting = confirmed.json()
    assert posting["evaluation_status"] == "failed"
    assert posting["evaluation_failure"] == {"kind": "missing_input", "reason": reason}
    assert submitted.json()["status"] == "failed"
    assert submitted.json()["failure"] == {"kind": "missing_input", "reason": reason}
    await run_queued_tasks()
    assert len(fake_llm.connections) == 1  # only the first Clipping's extraction
