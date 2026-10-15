import httpx


async def test_a_saved_document_is_its_current_version(client: httpx.AsyncClient) -> None:
    saved = await client.post(
        "/api/documents/career-profile/versions", json={"text": "Ten years of data engineering."}
    )
    assert saved.status_code == 201

    current = (await client.get("/api/documents/career-profile")).json()

    assert current["id"] == saved.json()["id"]
    assert current["kind"] == "career-profile"
    assert current["number"] == 1
    assert current["text"] == "Ten years of data engineering."


async def test_saving_again_adds_a_version_and_keeps_the_previous_one(
    client: httpx.AsyncClient,
) -> None:
    first = (
        await client.post("/api/documents/preferences/versions", json={"text": "Data platforms."})
    ).json()
    second = (
        await client.post(
            "/api/documents/preferences/versions", json={"text": "Data platforms, remote."}
        )
    ).json()

    current = (await client.get("/api/documents/preferences")).json()
    assert current["id"] == second["id"] != first["id"]
    assert current["number"] == 2
    assert current["text"] == "Data platforms, remote."

    previous = await client.get(f"/api/documents/preferences/versions/{first['id']}")
    assert previous.status_code == 200
    assert previous.json() == first


async def test_each_document_has_its_own_versions(client: httpx.AsyncClient) -> None:
    profile = (
        await client.post("/api/documents/career-profile/versions", json={"text": "Spark, Kafka."})
    ).json()

    unwritten = await client.get("/api/documents/writing-guide")
    assert unwritten.status_code == 200
    assert unwritten.json() is None

    guide = (
        await client.post("/api/documents/writing-guide/versions", json={"text": "Short, plain."})
    ).json()
    assert guide["number"] == 1

    other_kind = await client.get(f"/api/documents/writing-guide/versions/{profile['id']}")
    assert other_kind.status_code == 404


async def test_saving_blank_text_clears_the_document_and_keeps_the_previous_version(
    client: httpx.AsyncClient,
) -> None:
    first = (
        await client.post("/api/documents/preferences/versions", json={"text": "Data platforms."})
    ).json()

    cleared = await client.post("/api/documents/preferences/versions", json={"text": ""})
    assert cleared.status_code == 201

    current = (await client.get("/api/documents/preferences")).json()
    assert current["id"] == cleared.json()["id"] != first["id"]
    assert current["number"] == 2
    assert current["text"] == ""

    previous = await client.get(f"/api/documents/preferences/versions/{first['id']}")
    assert previous.json() == first
