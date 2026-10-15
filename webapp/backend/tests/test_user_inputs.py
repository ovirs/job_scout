from collections.abc import Awaitable, Callable

import httpx


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
