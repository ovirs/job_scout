from collections.abc import Awaitable, Callable

import httpx

POSTING = {
    "title": "Senior Data Engineer",
    "company": "Acme",
    "location_text": "Bucharest, Romania",
    "description": "Build and run our batch and streaming pipelines.",
}


async def test_a_saved_job_posting_is_listed_and_processed_by_the_worker(
    client: httpx.AsyncClient, run_queued_tasks: Callable[[], Awaitable[None]]
) -> None:
    saved = await client.post("/api/job-postings", json=POSTING)
    assert saved.status_code == 201
    assert saved.json()["processing_status"] == "queued"

    listed = (await client.get("/api/job-postings")).json()
    assert [{k: p[k] for k in POSTING} for p in listed] == [POSTING]
    assert listed[0]["id"] == saved.json()["id"]
    assert listed[0]["processing_status"] == "queued"

    await run_queued_tasks()

    listed = (await client.get("/api/job-postings")).json()
    assert listed[0]["processing_status"] == "processed"


async def test_the_list_shows_the_newest_job_posting_first(client: httpx.AsyncClient) -> None:
    for title in ["Data Engineer", "Analytics Engineer", "Platform Engineer"]:
        await client.post("/api/job-postings", json={**POSTING, "title": title})

    listed = (await client.get("/api/job-postings")).json()

    assert [p["title"] for p in listed] == [
        "Platform Engineer",
        "Analytics Engineer",
        "Data Engineer",
    ]
