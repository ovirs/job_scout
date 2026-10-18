from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from test_applications import start
from test_evaluations import write_career_profile
from test_triage import add_posting

from job_scout.llm.fake import FakeLlm

RunTasks = Callable[[], Awaitable[None]]


async def add_posting_note(client: httpx.AsyncClient, posting_id: int, text: str) -> httpx.Response:
    return await client.post(f"/api/job-postings/{posting_id}/notes", json={"text": text})


async def posting_notes(client: httpx.AsyncClient, posting_id: int) -> list[dict[str, Any]]:
    response = await client.get(f"/api/job-postings/{posting_id}/notes")
    assert response.status_code == 200
    found: list[dict[str, Any]] = response.json()
    return found


async def test_a_note_added_to_a_posting_is_listed_dated_on_the_posting(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Data Engineer")

    added = await add_posting_note(client, posting_id, "Recruiter is Ana, met at the meetup")
    await add_posting_note(client, posting_id, "Salary band asked")

    assert added.status_code == 201
    note = added.json()
    assert note["text"] == "Recruiter is Ana, met at the meetup"
    assert note["job_posting_id"] == posting_id
    assert note["application_id"] is None
    assert note["created_at"]
    notes = await posting_notes(client, posting_id)
    assert [n["text"] for n in notes] == [
        "Recruiter is Ana, met at the meetup",
        "Salary band asked",
    ]


async def add_application_note(
    client: httpx.AsyncClient, application_id: int, text: str
) -> httpx.Response:
    return await client.post(f"/api/applications/{application_id}/notes", json={"text": text})


async def application_notes(client: httpx.AsyncClient, application_id: int) -> list[dict[str, Any]]:
    response = await client.get(f"/api/applications/{application_id}/notes")
    assert response.status_code == 200
    found: list[dict[str, Any]] = response.json()
    return found


async def test_an_application_lists_its_own_notes_and_its_postings_notes_in_date_order(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Data Engineer")
    await add_posting_note(client, posting_id, "Before applying: ask about on-call")
    application_id = (await start(client, posting_id)).json()["id"]

    added = await add_application_note(client, application_id, "Screen call with Ana on Monday")
    await add_posting_note(client, posting_id, "Glassdoor reviews are mixed")

    assert added.status_code == 201
    assert added.json()["application_id"] == application_id
    assert added.json()["job_posting_id"] is None
    assert [
        (n["text"], n["application_id"], n["job_posting_id"])
        for n in await application_notes(client, application_id)
    ] == [
        ("Before applying: ask about on-call", None, posting_id),
        ("Screen call with Ana on Monday", application_id, None),
        ("Glassdoor reviews are mixed", None, posting_id),
    ]
    assert [n["text"] for n in await posting_notes(client, posting_id)] == [
        "Before applying: ask about on-call",
        "Glassdoor reviews are mixed",
    ]


async def delete_note(client: httpx.AsyncClient, note_id: int) -> httpx.Response:
    return await client.delete(f"/api/notes/{note_id}")


async def test_a_deleted_note_is_hidden_everywhere(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Data Engineer")
    application_id = (await start(client, posting_id)).json()["id"]
    on_posting = (await add_posting_note(client, posting_id, "Typo'd note")).json()
    await add_posting_note(client, posting_id, "Kept on the posting")
    on_application = (await add_application_note(client, application_id, "Wrong round")).json()
    await add_application_note(client, application_id, "Kept on the Application")

    assert (await delete_note(client, on_posting["id"])).status_code == 204
    assert (await delete_note(client, on_application["id"])).status_code == 204

    assert [n["text"] for n in await posting_notes(client, posting_id)] == ["Kept on the posting"]
    assert [n["text"] for n in await application_notes(client, application_id)] == [
        "Kept on the posting",
        "Kept on the Application",
    ]
    assert (await delete_note(client, on_posting["id"])).status_code == 404


async def test_deleting_an_unknown_note_is_not_found(client: httpx.AsyncClient) -> None:
    assert (await delete_note(client, 999)).status_code == 404


async def test_a_deleted_applications_notes_stay_hidden_and_a_new_one_starts_without_them(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Data Engineer")
    first_id = (await start(client, posting_id)).json()["id"]
    await add_posting_note(client, posting_id, "On the posting")
    gone = (await add_application_note(client, first_id, "On the first Application")).json()
    await client.delete(f"/api/applications/{first_id}")

    second_id = (await start(client, posting_id)).json()["id"]

    assert [n["text"] for n in await application_notes(client, second_id)] == ["On the posting"]
    assert (await add_application_note(client, first_id, "Too late")).status_code == 404
    assert (await client.get(f"/api/applications/{first_id}/notes")).status_code == 404
    assert (await delete_note(client, gone["id"])).status_code == 404


async def test_a_blank_note_is_rejected_and_one_with_text_is_kept_as_written(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Data Engineer")
    application_id = (await start(client, posting_id)).json()["id"]

    assert (await add_posting_note(client, posting_id, "  \n ")).status_code == 422
    assert (await add_application_note(client, application_id, "")).status_code == 422
    kept = await add_posting_note(client, posting_id, "Round 1:\n  - system design\n")

    assert kept.json()["text"] == "Round 1:\n  - system design\n"
    assert [n["text"] for n in await application_notes(client, application_id)] == [
        "Round 1:\n  - system design\n"
    ]


async def test_notes_on_an_unknown_posting_or_application_are_not_found(
    client: httpx.AsyncClient,
) -> None:
    assert (await add_posting_note(client, 999, "Hello")).status_code == 404
    assert (await client.get("/api/job-postings/999/notes")).status_code == 404
    assert (await add_application_note(client, 999, "Hello")).status_code == 404
    assert (await client.get("/api/applications/999/notes")).status_code == 404
