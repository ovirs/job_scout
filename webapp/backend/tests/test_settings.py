"""Settings: the owner's Provider keys, checked against the Provider before they are saved,
and the setup gate that holds the app until a Provider is set up."""

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from clipping_helpers import ENVELOPE, PASTED_TEXT, an_extraction, submit_and_extract
from conftest import TEST_KEY
from test_applications import start
from test_evaluations import write_career_profile
from test_triage import add_posting

from job_scout.llm import Failure
from job_scout.llm.fake import FakeLlm, FakeModelLister

RunTasks = Callable[[], Awaitable[None]]

KEY = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz-a1b2"


async def save_key(
    client: httpx.AsyncClient, api_key: str, provider: str = "anthropic"
) -> httpx.Response:
    return await client.put(f"/api/settings/providers/{provider}/key", json={"api_key": api_key})


async def providers(client: httpx.AsyncClient) -> dict[str, dict[str, Any]]:
    response = await client.get("/api/settings/providers")
    assert response.status_code == 200
    return {entry["provider"]: entry for entry in response.json()}


async def test_a_saved_key_is_shown_only_masked_with_when_it_was_saved(
    client_without_provider: httpx.AsyncClient, fake_lister: FakeModelLister
) -> None:
    saved = await save_key(client_without_provider, KEY)

    assert saved.status_code == 200
    assert saved.json()["key"]["masked"] == "sk-…a1b2"
    assert saved.json()["key"]["saved_at"]
    listed = await providers(client_without_provider)
    assert listed["anthropic"]["key"]["masked"] == "sk-…a1b2"
    assert fake_lister.calls == [("anthropic", KEY)]
    assert KEY not in saved.text
    assert KEY not in (await client_without_provider.get("/api/settings/providers")).text


async def test_a_key_the_provider_refuses_is_not_saved_and_its_reason_is_returned(
    client_without_provider: httpx.AsyncClient, fake_lister: FakeModelLister
) -> None:
    fake_lister.refuse("invalid x-api-key")

    refused = await save_key(client_without_provider, KEY)

    assert refused.status_code == 422
    assert refused.json()["detail"] == "Anthropic refused the key: invalid x-api-key"
    assert (await providers(client_without_provider))["anthropic"]["key"] is None
    assert (await client_without_provider.get("/api/setup")).json() == {"has_provider": False}


async def test_a_replaced_key_is_shown_masked_in_place_of_the_old_one(
    client_without_provider: httpx.AsyncClient,
) -> None:
    await save_key(client_without_provider, KEY)

    replaced = await save_key(client_without_provider, "  sk-ant-api03-another-key-z9y8\n")

    assert replaced.status_code == 200
    assert replaced.json()["key"]["masked"] == "sk-…z9y8"
    assert (await providers(client_without_provider))["anthropic"]["key"]["masked"] == "sk-…z9y8"


async def test_only_a_provider_with_an_adapter_can_be_set_up(
    client_without_provider: httpx.AsyncClient, fake_lister: FakeModelLister
) -> None:
    listed = await providers(client_without_provider)

    refused = await save_key(client_without_provider, "sk-proj-abcdefghijkl", provider="openai")

    assert {name: entry["available"] for name, entry in listed.items()} == {
        "anthropic": True,
        "openai": False,
        "google": False,
    }
    assert refused.status_code == 409
    assert refused.json()["detail"] == "OpenAI is not available yet"
    assert fake_lister.calls == []


async def test_the_app_is_set_up_once_a_provider_has_a_key_and_not_after_the_last_is_removed(
    client_without_provider: httpx.AsyncClient,
) -> None:
    before = (await client_without_provider.get("/api/setup")).json()
    await save_key(client_without_provider, KEY)
    after_saving = (await client_without_provider.get("/api/setup")).json()

    removed = await client_without_provider.delete("/api/settings/providers/anthropic/key")

    assert before == {"has_provider": False}
    assert after_saving == {"has_provider": True}
    assert removed.status_code == 204
    assert (await client_without_provider.get("/api/setup")).json() == {"has_provider": False}
    assert (await providers(client_without_provider))["anthropic"]["key"] is None


async def test_removing_a_key_the_owner_does_not_have_is_a_404(
    client_without_provider: httpx.AsyncClient,
) -> None:
    removed = await client_without_provider.delete("/api/settings/providers/anthropic/key")

    assert removed.status_code == 404


async def test_with_no_provider_every_request_that_would_start_an_llm_run_is_refused(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    queued_tasks: Callable[[], Awaitable[list[str]]],
) -> None:
    await write_career_profile(client)
    clipping = await submit_and_extract(client, run_queued_tasks)
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Data Engineer")
    application_id = (await start(client, posting_id)).json()["id"]
    other_posting_id = await add_posting(
        client, fake_llm, run_queued_tasks, "Data Platform Engineer", evaluate=False
    )
    await client.delete("/api/settings/providers/anthropic/key")
    queued_before = await queued_tasks()  # the second posting's Evaluation, never run

    letter = f"/api/applications/{application_id}/cover-letter"
    refused = [
        await client.post("/api/clippings", json={"pasted_text": PASTED_TEXT}),
        await client.post(f"/api/clippings/{clipping['id']}/retry"),
        await client.post(f"/api/clippings/{clipping['id']}/confirm", json=ENVELOPE),
        await client.post(f"/api/job-postings/{posting_id}/evaluations"),
        await client.post("/api/evaluations/rerun-unacted"),
        await client.post(f"/api/job-postings/{other_posting_id}/applications"),
        await client.post(f"{letter}/generations", json={"evaluation_case": "current"}),
        await client.post(
            f"{letter}/revisions", json={"evaluation_case": "current", "instruction": "Shorter"}
        ),
    ]

    assert [response.status_code for response in refused] == [409] * len(refused)
    assert {response.json()["detail"] for response in refused} == {
        "Set up a Provider in Settings before running the LLM"
    }
    assert await queued_tasks() == queued_before


async def test_a_run_calls_the_provider_with_the_owners_key(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    clipping = await submit_and_extract(client, run_queued_tasks)

    assert clipping["status"] == "done"
    assert fake_llm.connections == [("anthropic", TEST_KEY)]


async def test_a_key_replaced_while_a_run_waits_is_used_on_its_next_attempt(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    async def replace_key(pasted_text: str) -> None:
        if len(fake_llm.connections) == 1:
            await save_key(client, KEY)

    fake_llm.manual_entry_extraction.while_answering(replace_key)
    fake_llm.manual_entry_extraction.respond_with(
        Failure("error", "invalid x-api-key"), an_extraction()
    )

    clipping = await submit_and_extract(client, run_queued_tasks)

    assert clipping["status"] == "done"
    assert fake_llm.connections == [("anthropic", TEST_KEY), ("anthropic", KEY)]


async def test_a_run_whose_owner_removed_their_key_fails_at_once_pointing_to_settings(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    submitted = await client.post("/api/clippings", json={"pasted_text": PASTED_TEXT})
    await client.delete("/api/settings/providers/anthropic/key")

    await run_queued_tasks()

    clipping = (await client.get(f"/api/clippings/{submitted.json()['id']}")).json()
    assert clipping["status"] == "failed"
    assert clipping["failure"] == {
        "kind": "missing_input",
        "reason": "There is no API key for Anthropic: add one in Settings",
    }
    assert fake_llm.connections == []
