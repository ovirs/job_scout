from collections.abc import Awaitable, Callable

import httpx
from clipping_helpers import save_manual_entry


async def test_a_saved_job_posting_is_listed_with_its_evaluation_status(
    client: httpx.AsyncClient, run_queued_tasks: Callable[[], Awaitable[None]]
) -> None:
    await client.post(
        "/api/documents/career-profile/versions", json={"text": "Ten years of Python."}
    )
    saved = await save_manual_entry(client, run_queued_tasks)
    assert saved["evaluation_status"] == "queued"

    listed = (await client.get("/api/job-postings")).json()
    assert [p["id"] for p in listed] == [saved["id"]]
    assert listed[0]["evaluation_status"] == "queued"

    await run_queued_tasks()

    listed = (await client.get("/api/job-postings")).json()
    assert listed[0]["evaluation_status"] == "done"


async def test_the_list_shows_the_newest_job_posting_first(
    client: httpx.AsyncClient, run_queued_tasks: Callable[[], Awaitable[None]]
) -> None:
    for title in ["Data Engineer", "Analytics Engineer", "Platform Engineer"]:
        await save_manual_entry(client, run_queued_tasks, title=title)

    listed = (await client.get("/api/job-postings")).json()

    assert [p["title"] for p in listed] == [
        "Platform Engineer",
        "Analytics Engineer",
        "Data Engineer",
    ]


async def test_an_unknown_job_posting_is_not_found(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/job-postings/1")).status_code == 404
