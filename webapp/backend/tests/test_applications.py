import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from test_evaluations import write_career_profile
from test_triage import add_posting, triage

from job_scout import db
from job_scout.config import Settings
from job_scout.job_postings import domain as job_postings
from job_scout.job_postings.models import JobPosting
from job_scout.llm.fake import FakeLlm

RunTasks = Callable[[], Awaitable[None]]
QueuedTasks = Callable[[], Awaitable[list[str]]]


async def start(client: httpx.AsyncClient, posting_id: int) -> httpx.Response:
    return await client.post(f"/api/job-postings/{posting_id}/applications")


async def posting(client: httpx.AsyncClient, posting_id: int) -> dict[str, Any]:
    found: dict[str, Any] = (await client.get(f"/api/job-postings/{posting_id}")).json()
    return found


async def test_starting_an_application_puts_it_in_preparing_and_the_posting_at_interested(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Data Engineer")

    started = await start(client, posting_id)

    assert started.status_code == 201
    application = started.json()
    assert application["job_posting_id"] == posting_id
    assert application["state"] == "preparing"
    assert application["closed"] is False
    found = await posting(client, posting_id)
    assert found["triage"]["value"] == "interested"
    assert found["triage"]["origin"] == "user"
    assert found["application"] == {"id": application["id"], "state": "preparing"}


async def test_of_two_simultaneous_starts_one_is_created_and_one_refused(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Data Engineer")

    responses = await asyncio.gather(start(client, posting_id), start(client, posting_id))

    assert sorted(response.status_code for response in responses) == [201, 409]
    [created] = [response.json() for response in responses if response.status_code == 201]
    assert (await posting(client, posting_id))["application"]["id"] == created["id"]


async def test_starting_an_application_on_an_unknown_posting_is_not_found(
    client: httpx.AsyncClient,
) -> None:
    assert (await start(client, 999)).status_code == 404


async def test_the_triage_is_locked_at_interested_while_the_application_is_live(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Data Engineer")
    await triage(client, posting_id, "maybe")
    await start(client, posting_id)

    for value in ("ignored", "maybe", "interested"):
        assert (await triage(client, posting_id, value)).status_code == 409
    assert (await posting(client, posting_id))["triage"]["value"] == "interested"


async def move(client: httpx.AsyncClient, application_id: int, state: str) -> httpx.Response:
    return await client.put(f"/api/applications/{application_id}/state", json={"state": state})


async def started_application(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks, title: str = "Role"
) -> dict[str, Any]:
    """Save and evaluate a posting titled `title` and start an Application on it."""
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, title)
    application: dict[str, Any] = (await start(client, posting_id)).json()
    return application


async def test_an_application_moves_between_any_two_states_each_move_dated_in_its_history(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks)
    path = ["offer", "applied", "rejected", "preparing", "no_response", "interview_loop"]

    for state in path:
        moved = await move(client, application["id"], state)
        assert moved.status_code == 200
        assert moved.json()["state"] == state

    found = (await client.get(f"/api/applications/{application['id']}")).json()
    assert found["state"] == "interview_loop"
    history = found["history"]
    assert [change["state"] for change in history] == ["preparing", *path]
    dates = [change["changed_at"] for change in history]
    assert all(dates) and dates == sorted(dates)
    assert found["state_changed_at"] == dates[-1]
    assert found["closed"] is False
    assert found["posting_copy"]["title"] == "Role"  # taken on the move to Applied


async def test_an_unknown_state_is_rejected(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks)

    assert (await move(client, application["id"], "ghosted")).status_code == 422


async def test_an_unknown_application_is_not_found(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/applications/999")).status_code == 404
    assert (await move(client, 999, "applied")).status_code == 404


async def edit_posting_text(
    settings: Settings, posting_id: int, *, title: str, description: str
) -> None:
    """Change the posting's text through its update path. Phase 1 offers the user no
    action for it; Pipelines will use it."""
    engine = db.create_engine(settings)
    try:
        async with db.create_sessionmaker(engine)() as session:
            found = await session.get(JobPosting, posting_id)
            assert found is not None
            job_postings.set_text(
                found, title=title, location_text=found.location_text, description=description
            )
            await session.commit()
    finally:
        await engine.dispose()


async def delete(client: httpx.AsyncClient, application_id: int) -> httpx.Response:
    return await client.delete(f"/api/applications/{application_id}")


async def test_a_deleted_application_is_hidden_and_the_triage_freed_at_interested(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks)
    posting_id = application["job_posting_id"]

    deleted = await delete(client, application["id"])

    assert deleted.status_code == 204
    assert (await client.get(f"/api/applications/{application['id']}")).status_code == 404
    assert (await move(client, application["id"], "applied")).status_code == 404
    assert (await delete(client, application["id"])).status_code == 404
    found = await posting(client, posting_id)
    assert found["application"] is None
    assert found["triage"]["value"] == "interested"
    assert (await triage(client, posting_id, "maybe")).status_code == 200


async def test_an_application_past_preparing_cannot_be_deleted(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks)

    for state in ("applied", "screen_call", "withdrawn"):
        await move(client, application["id"], state)
        assert (await delete(client, application["id"])).status_code == 409

    found = await client.get(f"/api/applications/{application['id']}")
    assert found.json()["state"] == "withdrawn"


async def listed(client: httpx.AsyncClient, **params: str) -> list[tuple[str, str]]:
    response = await client.get("/api/applications", params=params)
    assert response.status_code == 200
    return [(row["job_posting_title"], row["state"]) for row in response.json()]


async def test_the_applications_list_is_ordered_by_state_and_splits_in_flight_from_closed(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    for title, path in [
        ("Rejected one", ["applied", "rejected"]),
        ("Interviewing", ["applied", "interview_loop"]),
        ("Preparing", []),
        ("Deleted", None),
        ("Offered", ["offer"]),
        ("Accepted one", ["accepted"]),
    ]:
        application = await started_application(client, fake_llm, run_queued_tasks, title)
        if path is None:
            await delete(client, application["id"])
        for state in path or []:
            await move(client, application["id"], state)

    assert await listed(client) == [
        ("Preparing", "preparing"),
        ("Interviewing", "interview_loop"),
        ("Offered", "offer"),
        ("Accepted one", "accepted"),
        ("Rejected one", "rejected"),
    ]
    assert await listed(client, closed="false") == [
        ("Preparing", "preparing"),
        ("Interviewing", "interview_loop"),
        ("Offered", "offer"),
    ]
    assert await listed(client, closed="true") == [
        ("Accepted one", "accepted"),
        ("Rejected one", "rejected"),
    ]


async def test_list_rows_show_the_posting_as_it_is_now(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks, "Data Engineer")
    await client.post(f"/api/job-postings/{application['job_posting_id']}/close")

    [row] = (await client.get("/api/applications")).json()

    assert row["job_posting_title"] == "Data Engineer"
    assert row["job_posting_company"] == "Acme"
    assert row["job_posting_closed_at"] is not None
