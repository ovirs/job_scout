"""The models the app offers: each Provider's listing for the owner's key, cached for a
day, with the owner's hidden models and dated snapshots left out."""

from datetime import timedelta
from typing import Any

import httpx
import psycopg
from conftest import TEST_KEY

from job_scout import db
from job_scout.config import Settings
from job_scout.llm.fake import OPUS, FakeModelLister
from job_scout.llm.interface import ListedModel, Provider
from job_scout.owners import LOCAL_USER_ID
from job_scout.settings import domain as provider_settings

HAIKU_SNAPSHOT = ListedModel(
    provider="anthropic",
    id="claude-haiku-4-5-20251001",
    display_name="Claude Haiku 4.5",
    snapshot=True,
    efforts=(),
)

SONNET = ListedModel(
    provider="anthropic",
    id="claude-sonnet-5",
    display_name="Claude Sonnet 5",
    snapshot=False,
    efforts=("low", "medium", "high"),
)

OPUS_OFFERED = {
    "provider": "anthropic",
    "id": "claude-opus-5-5",
    "display_name": "Claude Opus 5.5",
    "snapshot": False,
    "efforts": ["low", "medium", "high", "xhigh", "max"],
}


async def offered(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    response = await client.get("/api/models")
    assert response.status_code == 200
    result: list[dict[str, Any]] = response.json()
    return result


async def offered_ids(client: httpx.AsyncClient) -> list[str]:
    return [model["id"] for model in await offered(client)]


async def models_settings(client: httpx.AsyncClient) -> dict[str, Any]:
    response = await client.get("/api/settings/models")
    assert response.status_code == 200
    result: dict[str, Any] = response.json()
    return result


async def refresh(client: httpx.AsyncClient) -> dict[str, Any]:
    response = await client.post("/api/settings/models/refresh")
    assert response.status_code == 200
    result: dict[str, Any] = response.json()
    return result


async def show_snapshots(client: httpx.AsyncClient, show: bool) -> httpx.Response:
    return await client.put("/api/settings/show-snapshots", json={"show_snapshots": show})


async def test_the_models_offered_are_those_listed_for_the_key_without_dated_snapshots(
    client_without_provider: httpx.AsyncClient, fake_lister: FakeModelLister
) -> None:
    fake_lister.listings["anthropic"] = [OPUS, HAIKU_SNAPSHOT]
    await client_without_provider.put(
        "/api/settings/providers/anthropic/key", json={"api_key": "sk-ant-api03-a-key-a1b2"}
    )

    assert await offered(client_without_provider) == [OPUS_OFFERED]


async def test_dated_snapshots_are_offered_once_the_owner_shows_them_and_not_after(
    client: httpx.AsyncClient, fake_lister: FakeModelLister
) -> None:
    fake_lister.listings["anthropic"] = [OPUS, HAIKU_SNAPSHOT]
    await refresh(client)

    shown = await show_snapshots(client, True)
    with_snapshots = await offered_ids(client)
    await show_snapshots(client, False)

    assert shown.status_code == 204
    assert with_snapshots == ["claude-opus-5-5", "claude-haiku-4-5-20251001"]
    assert await offered_ids(client) == ["claude-opus-5-5"]
    assert (await models_settings(client))["show_snapshots"] is False


async def test_a_hidden_model_is_not_offered_but_stays_listed_in_settings_to_offer_again(
    client: httpx.AsyncClient, fake_lister: FakeModelLister
) -> None:
    fake_lister.listings["anthropic"] = [OPUS, SONNET]
    await refresh(client)

    hidden = await client.put("/api/settings/hidden-models/anthropic/claude-opus-5-5")
    offered_while_hidden = await offered_ids(client)
    listed_while_hidden = await models_settings(client)
    shown = await client.delete("/api/settings/hidden-models/anthropic/claude-opus-5-5")

    assert (hidden.status_code, shown.status_code) == (204, 204)
    assert offered_while_hidden == ["claude-sonnet-5"]
    [anthropic] = listed_while_hidden["providers"]
    assert {model["id"]: model["hidden"] for model in anthropic["models"]} == {
        "claude-opus-5-5": True,
        "claude-sonnet-5": False,
    }
    assert await offered_ids(client) == ["claude-opus-5-5", "claude-sonnet-5"]


async def test_the_listing_saved_with_the_key_is_used_for_a_day_then_fetched_again(
    client: httpx.AsyncClient, fake_lister: FakeModelLister, settings: Settings
) -> None:
    fake_lister.listings["anthropic"] = [OPUS, SONNET]  # released after the key was saved

    within_the_day = (await offered_ids(client), await models_settings(client))
    calls_within_the_day = list(fake_lister.calls)
    age_listings(settings, by=timedelta(days=1, minutes=1))
    after_a_day = await offered_ids(client)

    assert within_the_day[0] == ["claude-opus-5-5"]
    assert calls_within_the_day == [("anthropic", TEST_KEY)]  # when the key was saved
    assert after_a_day == ["claude-opus-5-5", "claude-sonnet-5"]
    assert fake_lister.calls == [("anthropic", TEST_KEY)] * 2
    assert await offered_ids(client) == after_a_day
    assert len(fake_lister.calls) == 2


async def test_refresh_fetches_the_listing_again_at_once(
    client: httpx.AsyncClient, fake_lister: FakeModelLister
) -> None:
    fake_lister.listings["anthropic"] = [OPUS, SONNET]

    refreshed = await refresh(client)

    [anthropic] = refreshed["providers"]
    assert [model["id"] for model in anthropic["models"]] == ["claude-opus-5-5", "claude-sonnet-5"]
    assert anthropic["refused"] is None
    assert fake_lister.calls == [("anthropic", TEST_KEY)] * 2
    assert await offered_ids(client) == ["claude-opus-5-5", "claude-sonnet-5"]


async def test_a_refresh_the_provider_refuses_keeps_the_list_from_before_with_its_reason(
    client: httpx.AsyncClient, fake_lister: FakeModelLister
) -> None:
    before = (await models_settings(client))["providers"][0]
    fake_lister.refuse("invalid x-api-key")

    refreshed = await refresh(client)

    [anthropic] = refreshed["providers"]
    assert anthropic["refused"] == "Anthropic refused the key: invalid x-api-key"
    assert anthropic["models"] == before["models"]
    assert anthropic["fetched_at"] == before["fetched_at"]
    assert await offered_ids(client) == ["claude-opus-5-5"]


async def test_no_models_are_offered_for_a_provider_whose_key_was_removed(
    client: httpx.AsyncClient,
) -> None:
    await client.delete("/api/settings/providers/anthropic/key")

    assert await offered(client) == []
    assert await models_settings(client) == {"show_snapshots": False, "providers": []}


async def test_a_model_is_usable_only_while_it_is_offered(
    client: httpx.AsyncClient, fake_lister: FakeModelLister, settings: Settings
) -> None:
    fake_lister.listings["anthropic"] = [OPUS, SONNET, HAIKU_SNAPSHOT]
    await refresh(client)
    await client.put("/api/settings/hidden-models/anthropic/claude-sonnet-5")

    listed = await usable(settings, fake_lister, "anthropic", "claude-opus-5-5")
    hidden = await usable(settings, fake_lister, "anthropic", "claude-sonnet-5")
    snapshot_while_off = await usable(settings, fake_lister, "anthropic", HAIKU_SNAPSHOT.id)
    unlisted = await usable(settings, fake_lister, "anthropic", "claude-opus-4-1")
    await show_snapshots(client, True)
    snapshot_while_on = await usable(settings, fake_lister, "anthropic", HAIKU_SNAPSHOT.id)
    calls = len(fake_lister.calls)
    await client.delete("/api/settings/providers/anthropic/key")
    key_removed = await usable(settings, fake_lister, "anthropic", "claude-opus-5-5")

    assert (listed, hidden, snapshot_while_off, unlisted) == (True, False, False, False)
    assert snapshot_while_on is True
    assert key_removed is False
    assert len(fake_lister.calls) == calls  # the check reads the cached listing only


async def test_a_model_of_a_provider_with_no_adapter_is_not_usable(
    client: httpx.AsyncClient, settings: Settings
) -> None:
    no_adapter = FakeModelLister()
    no_adapter.available = ()

    assert await usable(settings, no_adapter, "anthropic", "claude-opus-5-5") is False


async def usable(
    settings: Settings, lister: FakeModelLister, provider: Provider, model_id: str
) -> bool:
    engine = db.create_engine(settings)
    try:
        async with db.create_sessionmaker(engine)() as session:
            return await provider_settings.usable(
                session, lister, owner_id=LOCAL_USER_ID, provider=provider, model_id=model_id
            )
    finally:
        await engine.dispose()


def age_listings(settings: Settings, *, by: timedelta) -> None:
    """Make every cached listing look fetched `by` earlier."""
    with psycopg.connect(settings.database_url) as conn:
        conn.execute("UPDATE model_listings SET fetched_at = fetched_at - %(by)s", {"by": by})
