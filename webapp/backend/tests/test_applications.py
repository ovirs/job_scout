from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from test_evaluations import DESCRIPTION, write_career_profile
from test_triage import add_posting, triage

from job_scout import db, job_postings
from job_scout.config import Settings
from job_scout.llm import Failure
from job_scout.llm.fake import FakeLlm
from job_scout.models import JobPosting

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


async def test_a_second_live_application_for_a_posting_is_refused(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Data Engineer")
    first = (await start(client, posting_id)).json()

    second = await start(client, posting_id)

    assert second.status_code == 409
    assert (await posting(client, posting_id))["application"]["id"] == first["id"]


async def test_starting_an_application_on_an_unknown_posting_is_not_found(
    client: httpx.AsyncClient,
) -> None:
    assert (await start(client, 999)).status_code == 404


async def evaluation_statuses(client: httpx.AsyncClient, posting_id: int) -> list[str]:
    """The statuses of the posting's Evaluations, the latest first."""
    runs = (await client.get(f"/api/job-postings/{posting_id}/evaluations")).json()
    return [run["status"] for run in runs]


async def test_starting_an_application_on_a_posting_not_evaluated_queues_an_evaluation(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    queued_tasks: QueuedTasks,
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(
        client, fake_llm, run_queued_tasks, "Broken", result=Failure("error", "Overloaded")
    )

    await start(client, posting_id)

    assert await evaluation_statuses(client, posting_id) == ["queued", "not_evaluated"]
    assert await queued_tasks() == ["evaluate"]


async def test_starting_an_application_queues_no_evaluation_when_one_is_done_or_under_way(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    queued_tasks: QueuedTasks,
) -> None:
    await write_career_profile(client)
    evaluated = await add_posting(client, fake_llm, run_queued_tasks, "Evaluated")
    waiting = await add_posting(client, fake_llm, run_queued_tasks, "Waiting", evaluate=False)

    await start(client, evaluated)
    await start(client, waiting)

    assert await evaluation_statuses(client, evaluated) == ["done"]
    assert await evaluation_statuses(client, waiting) == ["queued"]
    assert await queued_tasks() == ["evaluate"]


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


async def test_the_closed_states_are_accepted_rejected_withdrawn_and_no_response(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks)
    closed = {}

    for state in [
        "preparing",
        "applied",
        "screen_call",
        "interview_loop",
        "offer",
        "accepted",
        "rejected",
        "withdrawn",
        "no_response",
    ]:
        closed[state] = (await move(client, application["id"], state)).json()["closed"]

    assert [state for state, is_closed in closed.items() if is_closed] == [
        "accepted",
        "rejected",
        "withdrawn",
        "no_response",
    ]


async def test_moving_to_the_current_state_records_nothing(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks)

    moved = await move(client, application["id"], "preparing")

    assert moved.status_code == 200
    assert [change["state"] for change in moved.json()["history"]] == ["preparing"]


async def test_an_unknown_state_is_rejected(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks)

    assert (await move(client, application["id"], "ghosted")).status_code == 422


async def test_an_unknown_application_is_not_found(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/applications/999")).status_code == 404
    assert (await move(client, 999, "applied")).status_code == 404


async def test_closing_an_application_leaves_the_triage_at_interested_and_locked(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks)
    posting_id = application["job_posting_id"]

    for state in ("applied", "rejected"):
        await move(client, application["id"], state)

    found = await posting(client, posting_id)
    assert found["triage"]["value"] == "interested"
    assert found["application"] == {"id": application["id"], "state": "rejected"}
    assert (await triage(client, posting_id, "ignored")).status_code == 409
    assert (await start(client, posting_id)).status_code == 409


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


async def test_the_first_move_to_applied_copies_the_posting(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks, "Data Engineer")
    assert application["posting_copy"] is None

    applied = (await move(client, application["id"], "applied")).json()

    copy = applied["posting_copy"]
    assert copy["title"] == "Data Engineer"
    assert copy["company"] == "Acme"
    assert copy["location_text"] == "Bucharest, Romania"
    assert copy["description"] == DESCRIPTION
    assert copy["url"] is None
    assert copy["copied_at"] == applied["state_changed_at"]
    assert applied["posting_changed_since_copy"] is False


async def test_the_posting_copy_never_changes_after_later_moves_or_posting_edits(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    settings: Settings,
) -> None:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks, "Data Engineer")
    copy = (await move(client, application["id"], "applied")).json()["posting_copy"]

    await edit_posting_text(
        settings, application["job_posting_id"], title="Staff Data Engineer", description="New"
    )
    for state in ("preparing", "screen_call", "applied", "offer"):
        await move(client, application["id"], state)

    found = (await client.get(f"/api/applications/{application['id']}")).json()
    assert found["posting_copy"] == copy
    assert found["posting_changed_since_copy"] is True
    assert (await posting(client, application["job_posting_id"]))["title"] == "Staff Data Engineer"


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


async def test_an_application_moved_back_to_preparing_can_be_deleted(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks)
    for state in ("applied", "preparing"):
        await move(client, application["id"], state)

    assert (await delete(client, application["id"])).status_code == 204


async def test_a_new_application_after_a_deletion_starts_clean(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    first = await started_application(client, fake_llm, run_queued_tasks)
    posting_id = first["job_posting_id"]
    await delete(client, first["id"])
    await triage(client, posting_id, "ignored")

    started = await start(client, posting_id)

    assert started.status_code == 201
    second = started.json()
    assert second["id"] != first["id"]
    assert second["state"] == "preparing"
    assert [change["state"] for change in second["history"]] == ["preparing"]
    assert second["posting_copy"] is None
    found = await posting(client, posting_id)
    assert found["triage"]["value"] == "interested"
    assert found["application"]["id"] == second["id"]


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


async def test_applications_in_the_same_state_are_listed_latest_move_first(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    first = await started_application(client, fake_llm, run_queued_tasks, "First applied")
    second = await started_application(client, fake_llm, run_queued_tasks, "Second applied")
    await move(client, first["id"], "applied")
    await move(client, second["id"], "applied")

    assert await listed(client) == [("Second applied", "applied"), ("First applied", "applied")]

    await move(client, first["id"], "preparing")
    await move(client, first["id"], "applied")

    assert await listed(client) == [("First applied", "applied"), ("Second applied", "applied")]


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
