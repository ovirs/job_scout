"""Settings and Provider keys, and the setup gate, through the HTTP API with the fake model
lister and the fake LLM. The autouse `provider_key` fixture has saved the Anthropic key."""

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from clipping_helpers import PASTED_TEXT

from job_scout.llm.fake import FakeLlm, FakeModelLister

RunTasks = Callable[[], Awaitable[None]]

NEW_KEY = "sk-ant-a-new-key-1234"


async def providers(client: httpx.AsyncClient) -> dict[str, dict[str, Any]]:
    listed = await client.get("/api/settings/providers")
    assert listed.status_code == 200
    return {entry["provider"]: entry for entry in listed.json()}


async def has_provider(client: httpx.AsyncClient) -> bool:
    status: bool = (await client.get("/api/setup")).json()["has_provider"]
    return status


async def remove_the_key(client: httpx.AsyncClient) -> None:
    assert (await client.delete("/api/settings/providers/anthropic")).status_code == 204


async def test_the_providers_are_listed_with_only_the_masked_key_and_when_it_was_saved(
    client: httpx.AsyncClient, provider_key: str
) -> None:
    listed = await providers(client)

    assert list(listed) == ["anthropic", "openai", "google"]
    assert [entry["available"] for entry in listed.values()] == [True, False, False]
    anthropic = listed["anthropic"]
    assert anthropic["masked_key"].endswith(provider_key[-4:])
    assert provider_key not in anthropic["masked_key"]
    assert anthropic["saved_at"] is not None
    assert (listed["openai"]["masked_key"], listed["openai"]["saved_at"]) == (None, None)


async def test_saving_a_key_lists_the_providers_models_with_it_and_stores_it(
    client: httpx.AsyncClient, model_lister: FakeModelLister
) -> None:
    await remove_the_key(client)

    saved = await client.put("/api/settings/providers/anthropic", json={"key": f" {NEW_KEY} "})

    assert saved.status_code == 200
    assert saved.json()["models"] == model_lister.models
    assert saved.json()["provider"]["masked_key"].endswith("1234")
    assert model_lister.listed == [("anthropic", NEW_KEY)]  # the key as typed, trimmed
    assert await has_provider(client)


async def test_a_key_the_provider_refuses_is_not_saved_and_the_reason_is_returned(
    client: httpx.AsyncClient, model_lister: FakeModelLister, provider_key: str
) -> None:
    model_lister.refuse(NEW_KEY, "invalid x-api-key")

    refused = await client.put("/api/settings/providers/anthropic", json={"key": NEW_KEY})

    assert refused.status_code == 422
    assert refused.json()["detail"] == "invalid x-api-key"
    stored = (await providers(client))["anthropic"]
    assert stored["masked_key"].endswith(provider_key[-4:])  # the earlier key is kept


async def test_a_refused_key_leaves_no_provider_when_there_was_none(
    client: httpx.AsyncClient, model_lister: FakeModelLister
) -> None:
    await remove_the_key(client)
    model_lister.refuse(NEW_KEY, "invalid x-api-key")

    await client.put("/api/settings/providers/anthropic", json={"key": NEW_KEY})

    assert (await providers(client))["anthropic"]["masked_key"] is None
    assert not await has_provider(client)


async def test_a_provider_without_an_adapter_cannot_be_set_up(
    client: httpx.AsyncClient, model_lister: FakeModelLister
) -> None:
    refused = await client.put("/api/settings/providers/openai", json={"key": "sk-openai-1234"})

    assert refused.status_code == 409
    assert model_lister.listed == []
    assert (await providers(client))["openai"]["masked_key"] is None


async def test_a_blank_key_is_rejected(client: httpx.AsyncClient) -> None:
    refused = await client.put("/api/settings/providers/anthropic", json={"key": "  "})

    assert refused.status_code == 422


async def test_no_response_ever_contains_a_full_key(
    client: httpx.AsyncClient, provider_key: str
) -> None:
    responses = [
        await client.get("/api/settings/providers"),
        await client.put("/api/settings/providers/anthropic", json={"key": NEW_KEY}),
        await client.get("/api/settings/providers"),
        await client.get("/api/setup"),
        await client.get("/openapi.json"),
    ]

    for response in responses:
        assert provider_key not in response.text
        assert NEW_KEY not in response.text


async def test_removing_a_key_removes_the_provider_and_removing_it_again_is_a_404(
    client: httpx.AsyncClient,
) -> None:
    await remove_the_key(client)

    assert (await providers(client))["anthropic"]["masked_key"] is None
    assert (await client.delete("/api/settings/providers/anthropic")).status_code == 404


async def test_with_a_provider_the_setup_status_says_so_and_removing_the_last_key_undoes_it(
    client: httpx.AsyncClient,
) -> None:
    assert await has_provider(client)

    await remove_the_key(client)

    assert not await has_provider(client)


async def test_every_endpoint_that_starts_an_llm_run_refuses_with_409_while_there_is_no_provider(
    client: httpx.AsyncClient, queued_tasks: Callable[[], Awaitable[list[str]]]
) -> None:
    await remove_the_key(client)
    starting = [
        ("POST", "/api/clippings", {"pasted_text": PASTED_TEXT}),
        ("POST", "/api/clippings/1/retry", None),
        ("POST", "/api/clippings/1/confirm", {}),
        ("POST", "/api/job-postings/1/evaluations", None),
        ("POST", "/api/job-postings/1/applications", None),
        ("POST", "/api/applications/1/cover-letter/generations", {}),
        ("POST", "/api/applications/1/cover-letter/revisions", {}),
    ]

    for method, path, body in starting:
        refused = await client.request(method, path, json=body)
        assert refused.status_code == 409, path
        assert "Provider key" in refused.json()["detail"], path

    assert await queued_tasks() == []


async def test_the_app_works_again_once_a_key_is_saved(
    client: httpx.AsyncClient, run_queued_tasks: RunTasks
) -> None:
    await remove_the_key(client)
    assert (
        await client.post("/api/clippings", json={"pasted_text": PASTED_TEXT})
    ).status_code == 409

    await client.put("/api/settings/providers/anthropic", json={"key": NEW_KEY})

    submitted = await client.post("/api/clippings", json={"pasted_text": PASTED_TEXT})
    assert submitted.status_code == 201
    await run_queued_tasks()
    assert (await client.get(f"/api/clippings/{submitted.json()['id']}")).json()["status"] == "done"


async def test_the_worker_makes_each_attempt_with_the_owners_key_read_afresh(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    provider_key: str,
) -> None:
    await client.post("/api/clippings", json={"pasted_text": PASTED_TEXT})
    await run_queued_tasks()
    assert fake_llm.keys_used == [provider_key]

    # Replaced while the worker is already running elsewhere: no restart is involved
    await client.put("/api/settings/providers/anthropic", json={"key": NEW_KEY})
    await client.post("/api/clippings", json={"pasted_text": PASTED_TEXT})
    await run_queued_tasks()

    assert fake_llm.keys_used == [provider_key, NEW_KEY]


async def test_a_run_whose_key_is_removed_before_it_starts_fails_naming_the_missing_key(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
) -> None:
    submitted = await client.post("/api/clippings", json={"pasted_text": PASTED_TEXT})
    await remove_the_key(client)

    await run_queued_tasks()

    clipping = (await client.get(f"/api/clippings/{submitted.json()['id']}")).json()
    assert clipping["status"] == "failed"
    assert clipping["failure"]["kind"] == "missing_input"
    assert "Provider key" in clipping["failure"]["reason"]
    assert fake_llm.keys_used == []
    assert fake_llm.manual_entry_extraction.calls == []
