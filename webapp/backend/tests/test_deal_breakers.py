import httpx

REMOTE = "Fully remote from Romania"
SPARK = "The role expects Spark experience: Spark is required or central to the daily work"


async def test_adding_deal_breakers_creates_a_new_version_of_the_set_each_time(
    client: httpx.AsyncClient,
) -> None:
    first = await client.post("/api/deal-breakers", json={"text": REMOTE})
    assert first.status_code == 201
    second = (await client.post("/api/deal-breakers", json={"text": SPARK})).json()

    current = (await client.get("/api/deal-breakers")).json()

    assert current["id"] == second["id"] != first.json()["id"]
    assert current["number"] == 2
    assert [d["text"] for d in current["deal_breakers"]] == [REMOTE, SPARK]


async def test_an_edited_deal_breaker_keeps_its_id_in_a_new_version_of_the_set(
    client: httpx.AsyncClient,
) -> None:
    await client.post("/api/deal-breakers", json={"text": "Remote"})
    before = (await client.post("/api/deal-breakers", json={"text": SPARK})).json()
    remote_id = before["deal_breakers"][0]["id"]

    edited = await client.put(f"/api/deal-breakers/{remote_id}", json={"text": REMOTE})
    assert edited.status_code == 200

    current = (await client.get("/api/deal-breakers")).json()
    assert current["id"] == edited.json()["id"] != before["id"]
    assert current["number"] == 3
    assert current["deal_breakers"] == [
        {"id": remote_id, "text": REMOTE},
        before["deal_breakers"][1],
    ]

    previous = await client.get(f"/api/deal-breakers/versions/{before['id']}")
    assert previous.status_code == 200
    assert previous.json() == before


async def test_a_deleted_deal_breaker_leaves_the_current_set_but_stays_in_earlier_versions(
    client: httpx.AsyncClient,
) -> None:
    await client.post("/api/deal-breakers", json={"text": REMOTE})
    before = (await client.post("/api/deal-breakers", json={"text": SPARK})).json()
    remote, spark = before["deal_breakers"]

    deleted = await client.delete(f"/api/deal-breakers/{remote['id']}")
    assert deleted.status_code == 200

    current = (await client.get("/api/deal-breakers")).json()
    assert current["id"] == deleted.json()["id"] != before["id"]
    assert current["number"] == 3
    assert current["deal_breakers"] == [spark]

    edit_again = await client.put(f"/api/deal-breakers/{remote['id']}", json={"text": "Remote"})
    assert edit_again.status_code == 404
    delete_again = await client.delete(f"/api/deal-breakers/{remote['id']}")
    assert delete_again.status_code == 404
    assert (await client.get("/api/deal-breakers")).json() == current

    previous = (await client.get(f"/api/deal-breakers/versions/{before['id']}")).json()
    assert previous == before


async def test_a_blank_deal_breaker_is_rejected_and_the_set_is_unchanged(
    client: httpx.AsyncClient,
) -> None:
    before = (await client.post("/api/deal-breakers", json={"text": REMOTE})).json()
    remote_id = before["deal_breakers"][0]["id"]

    added = await client.post("/api/deal-breakers", json={"text": "  "})
    edited = await client.put(f"/api/deal-breakers/{remote_id}", json={"text": ""})

    assert added.status_code == edited.status_code == 422
    assert (await client.get("/api/deal-breakers")).json() == before
