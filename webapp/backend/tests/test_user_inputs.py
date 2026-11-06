import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
import pytest

from job_scout.config import Settings
from job_scout.owners import LOCAL_USER_ID
from job_scout.runtime import Runtime, open_runtime
from job_scout.user_inputs import domain as user_inputs
from job_scout.user_inputs.models import DealBreakerSetVersion, DocumentVersion


async def test_editing_the_inputs_enqueues_nothing(
    client: httpx.AsyncClient, queued_tasks: Callable[[], Awaitable[list[str]]]
) -> None:
    for kind in ["career-profile", "preferences", "writing-guide"]:
        await client.post(f"/api/documents/{kind}/versions", json={"text": "First version"})
    added = (await client.post("/api/deal-breakers", json={"text": "Remote"})).json()
    deal_breaker_id = added["deal_breakers"][0]["id"]
    await client.put(f"/api/deal-breakers/{deal_breaker_id}", json={"text": "Fully remote"})
    await client.delete(f"/api/deal-breakers/{deal_breaker_id}")

    assert await queued_tasks() == []


@pytest.fixture
async def runtime(settings: Settings) -> AsyncIterator[Runtime]:
    async with open_runtime(settings) as runtime:
        yield runtime


async def save_document(runtime: Runtime, text: str) -> DocumentVersion:
    async with runtime.sessions() as session:
        version = await user_inputs.save_document(
            session, owner_id=LOCAL_USER_ID, kind="career-profile", text=text
        )
        await session.commit()
        return version


async def add_deal_breaker(runtime: Runtime, text: str) -> DealBreakerSetVersion:
    async with runtime.sessions() as session:
        version = await user_inputs.add_deal_breaker(session, owner_id=LOCAL_USER_ID, text=text)
        await session.commit()
        return version


@pytest.mark.parametrize("earlier", [0, 1])
async def test_two_simultaneous_saves_of_a_document_both_succeed_one_after_the_other(
    runtime: Runtime, earlier: int
) -> None:
    for n in range(earlier):
        await save_document(runtime, f"Earlier {n}")

    saved = await asyncio.gather(save_document(runtime, "One"), save_document(runtime, "Two"))

    assert sorted(version.number for version in saved) == [earlier + 1, earlier + 2]


@pytest.mark.parametrize("earlier", [0, 1])
async def test_two_simultaneous_deal_breaker_changes_both_succeed_one_after_the_other(
    runtime: Runtime, earlier: int
) -> None:
    for n in range(earlier):
        await add_deal_breaker(runtime, f"Earlier {n}")

    saved = await asyncio.gather(
        add_deal_breaker(runtime, "Remote"), add_deal_breaker(runtime, "No Spark")
    )

    assert sorted(version.number for version in saved) == [earlier + 1, earlier + 2]
    latest = max(saved, key=lambda version: version.number)
    assert sorted(item.text for item in latest.items) == sorted(
        ["No Spark", "Remote", *(f"Earlier {n}" for n in range(earlier))]
    )
