"""The Application rules, at the package's interface: starting one, moving it, deleting
it, and the Triage of a posting while it has one."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import get_args

import httpx
import pytest
from test_applications import edit_posting_text
from test_evaluations import DESCRIPTION, write_career_profile
from test_triage import add_posting

from job_scout.applications import domain as applications
from job_scout.applications.models import Application, ApplicationState
from job_scout.config import Settings
from job_scout.job_postings import domain as job_postings
from job_scout.job_postings.models import JobPosting
from job_scout.llm import Failure
from job_scout.llm.fake import FakeLlm, FakeModelLister
from job_scout.owners import LOCAL_USER_ID
from job_scout.posting_view import domain as posting_view
from job_scout.posting_view.schemas import JobPostingRead
from job_scout.runtime import Runtime, open_runtime
from job_scout.triage.models import TriageValue

RunTasks = Callable[[], Awaitable[None]]
QueuedTasks = Callable[[], Awaitable[list[str]]]


@pytest.fixture
async def runtime(settings: Settings) -> AsyncIterator[Runtime]:
    async with open_runtime(settings) as runtime:
        yield runtime


@pytest.fixture
async def posting_id(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> int:
    """An evaluated posting, untriaged, with no Application."""
    await write_career_profile(client)
    return await add_posting(client, fake_llm, run_queued_tasks, "Data Engineer")


async def start(runtime: Runtime, posting_id: int) -> Application:
    async with runtime.sessions() as session:
        return await applications.start(
            session,
            runtime.task_queue,
            FakeModelLister(),
            owner_id=LOCAL_USER_ID,
            job_posting_id=posting_id,
        )


async def read_posting(runtime: Runtime, posting_id: int) -> JobPostingRead:
    async with runtime.sessions() as session:
        found = await job_postings.job_posting(
            session, owner_id=LOCAL_USER_ID, job_posting_id=posting_id
        )
        assert found is not None
        return await posting_view.read(session, found)


async def test_starting_puts_the_application_in_preparing_and_the_posting_at_interested(
    runtime: Runtime, posting_id: int
) -> None:
    application = await start(runtime, posting_id)

    assert application.state == "preparing"
    assert [change.state for change in application.history] == ["preparing"]
    found = await read_posting(runtime, posting_id)
    assert found.triage is not None and found.triage.value == "interested"
    assert found.application is not None and found.application.id == application.id


async def test_of_two_simultaneous_starts_one_is_refused_as_already_applying(
    runtime: Runtime, posting_id: int
) -> None:
    outcomes = await asyncio.gather(
        start(runtime, posting_id), start(runtime, posting_id), return_exceptions=True
    )

    [started] = [o for o in outcomes if isinstance(o, Application)]
    [refused] = [o for o in outcomes if not isinstance(o, Application)]
    assert isinstance(refused, applications.AlreadyApplying)
    found = await read_posting(runtime, posting_id)
    assert found.application is not None and found.application.id == started.id


async def set_triage(runtime: Runtime, posting_id: int, value: TriageValue) -> JobPosting:
    async with runtime.sessions() as session:
        return await applications.set_triage(
            session, owner_id=LOCAL_USER_ID, job_posting_id=posting_id, value=value
        )


async def triage_value(runtime: Runtime, posting_id: int) -> str | None:
    found = (await read_posting(runtime, posting_id)).triage
    return None if found is None else found.value


async def test_the_triage_can_be_set_and_changed_recording_when(
    runtime: Runtime, posting_id: int
) -> None:
    await set_triage(runtime, posting_id, "maybe")
    first = (await read_posting(runtime, posting_id)).triage
    await set_triage(runtime, posting_id, "ignored")
    second = (await read_posting(runtime, posting_id)).triage

    assert first is not None and second is not None
    assert (first.value, first.origin) == ("maybe", "user")
    assert (second.value, second.origin) == ("ignored", "user")
    assert second.created_at == first.created_at  # when it was first triaged
    assert second.changed_at >= first.changed_at


@pytest.mark.parametrize("state", ["preparing", "applied", "rejected"])
async def test_the_triage_is_locked_at_interested_while_the_posting_has_a_live_application(
    runtime: Runtime, posting_id: int, state: ApplicationState
) -> None:
    application = await start(runtime, posting_id)
    await move(runtime, application.id, state)

    for value in ("ignored", "maybe", "interested"):
        with pytest.raises(applications.TriageLocked):
            await set_triage(runtime, posting_id, value)
    assert await triage_value(runtime, posting_id) == "interested"


async def test_two_simultaneous_first_triages_both_apply_one_after_the_other(
    runtime: Runtime, posting_id: int
) -> None:
    await asyncio.gather(
        set_triage(runtime, posting_id, "maybe"), set_triage(runtime, posting_id, "ignored")
    )

    assert await triage_value(runtime, posting_id) in ("maybe", "ignored")


async def test_a_triage_set_while_an_application_starts_cannot_unlock_it(
    runtime: Runtime, posting_id: int
) -> None:
    outcomes = await asyncio.gather(
        start(runtime, posting_id),
        set_triage(runtime, posting_id, "ignored"),
        return_exceptions=True,
    )

    assert isinstance(outcomes[0], Application)
    # Set before the start, or refused after it
    assert isinstance(outcomes[1], JobPosting | applications.TriageLocked)
    assert await triage_value(runtime, posting_id) == "interested"


async def move(runtime: Runtime, application_id: int, state: ApplicationState) -> Application:
    async with runtime.sessions() as session:
        return await applications.move(
            session, owner_id=LOCAL_USER_ID, application_id=application_id, state=state
        )


async def delete(runtime: Runtime, application_id: int) -> None:
    async with runtime.sessions() as session:
        await applications.delete(session, owner_id=LOCAL_USER_ID, application_id=application_id)


async def test_a_deleted_application_is_hidden_and_the_triage_freed_at_interested(
    runtime: Runtime, posting_id: int
) -> None:
    application = await start(runtime, posting_id)

    await delete(runtime, application.id)

    for change in [move(runtime, application.id, "applied"), delete(runtime, application.id)]:
        with pytest.raises(applications.NoSuchApplication):
            await change
    found = await read_posting(runtime, posting_id)
    assert found.application is None
    assert await triage_value(runtime, posting_id) == "interested"
    await set_triage(runtime, posting_id, "maybe")
    assert await triage_value(runtime, posting_id) == "maybe"


@pytest.mark.parametrize("state", ["applied", "screen_call", "withdrawn"])
async def test_an_application_past_preparing_cannot_be_deleted(
    runtime: Runtime, posting_id: int, state: ApplicationState
) -> None:
    application = await start(runtime, posting_id)
    await move(runtime, application.id, state)

    with pytest.raises(applications.NotDeletable):
        await delete(runtime, application.id)

    assert (await read_posting(runtime, posting_id)).application is not None


async def test_an_application_moved_back_to_preparing_can_be_deleted(
    runtime: Runtime, posting_id: int
) -> None:
    application = await start(runtime, posting_id)
    for state in ("applied", "preparing"):
        await move(runtime, application.id, state)

    await delete(runtime, application.id)

    assert (await read_posting(runtime, posting_id)).application is None


async def test_an_application_moving_to_applied_while_it_is_deleted_is_not_deleted(
    runtime: Runtime, posting_id: int
) -> None:
    application = await start(runtime, posting_id)

    async with runtime.sessions() as moving:
        # The move is under way: it holds the Application when the delete begins
        await applications.application(
            moving, owner_id=LOCAL_USER_ID, application_id=application.id, for_update=True
        )
        deleting = asyncio.create_task(delete(runtime, application.id))
        await asyncio.sleep(0.2)
        await applications.move(
            moving, owner_id=LOCAL_USER_ID, application_id=application.id, state="applied"
        )

    with pytest.raises(applications.NotDeletable):
        await deleting
    assert (await read_posting(runtime, posting_id)).application is not None


async def test_an_unknown_posting_or_application_is_reported_as_such(runtime: Runtime) -> None:
    for on_posting in [start(runtime, 999), set_triage(runtime, 999, "maybe")]:
        with pytest.raises(applications.NoSuchJobPosting):
            await on_posting
    for on_application in [move(runtime, 999, "applied"), delete(runtime, 999)]:
        with pytest.raises(applications.NoSuchApplication):
            await on_application


async def evaluation_statuses(client: httpx.AsyncClient, posting_id: int) -> list[str]:
    """The statuses of the posting's Evaluations, the latest first."""
    runs = (await client.get(f"/api/job-postings/{posting_id}/evaluations")).json()
    return [run["status"] for run in runs]


async def test_starting_on_a_posting_not_evaluated_queues_an_evaluation(
    runtime: Runtime,
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    queued_tasks: QueuedTasks,
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(
        client, fake_llm, run_queued_tasks, "Broken", result=Failure("error", "Overloaded")
    )

    await start(runtime, posting_id)

    assert await evaluation_statuses(client, posting_id) == ["queued", "failed"]
    assert await queued_tasks() == ["evaluate"]


async def test_starting_queues_no_evaluation_when_one_is_done_or_under_way(
    runtime: Runtime,
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    queued_tasks: QueuedTasks,
) -> None:
    await write_career_profile(client)
    evaluated = await add_posting(client, fake_llm, run_queued_tasks, "Evaluated")
    waiting = await add_posting(client, fake_llm, run_queued_tasks, "Waiting", evaluate=False)

    await start(runtime, evaluated)
    await start(runtime, waiting)

    assert await evaluation_statuses(client, evaluated) == ["done"]
    assert await evaluation_statuses(client, waiting) == ["queued"]
    assert await queued_tasks() == ["evaluate"]


async def test_starting_replaces_a_stuck_evaluation(
    runtime: Runtime,
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    make_stuck: Callable[[str, int], None],
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Stuck", evaluate=False)
    [stuck] = (await client.get(f"/api/job-postings/{posting_id}/evaluations")).json()
    make_stuck("evaluations", stuck["id"])

    await start(runtime, posting_id)

    assert await evaluation_statuses(client, posting_id) == ["queued", "failed"]


async def test_moves_between_any_two_states_are_each_dated_in_the_history(
    runtime: Runtime, posting_id: int
) -> None:
    application = await start(runtime, posting_id)
    path: list[ApplicationState] = ["offer", "applied", "rejected", "preparing", "interview_loop"]

    for state in path:
        moved = await move(runtime, application.id, state)
        assert moved.state == state

    assert [change.state for change in moved.history] == ["preparing", *path]
    dates = [change.changed_at for change in moved.history]
    assert dates == sorted(dates)
    assert applications.state_changed_at(moved) == dates[-1]


async def test_moving_to_the_current_state_records_nothing(
    runtime: Runtime, posting_id: int
) -> None:
    application = await start(runtime, posting_id)

    moved = await move(runtime, application.id, "preparing")

    assert [change.state for change in moved.history] == ["preparing"]


async def test_the_closed_states_are_accepted_rejected_withdrawn_and_no_response(
    runtime: Runtime, posting_id: int
) -> None:
    application = await start(runtime, posting_id)
    closed = {}

    for state in get_args(ApplicationState):
        closed[state] = applications.is_closed(await move(runtime, application.id, state))

    assert [state for state, is_closed in closed.items() if is_closed] == [
        "accepted",
        "rejected",
        "withdrawn",
        "no_response",
    ]


async def test_the_first_move_to_applied_copies_the_posting(
    runtime: Runtime, posting_id: int
) -> None:
    application = await start(runtime, posting_id)
    assert application.copied_at is None
    assert applications.posting_changed_since_copy(application) is None

    applied = await move(runtime, application.id, "applied")

    assert applied.copy_title == "Data Engineer"
    assert applied.copy_company == "Acme"
    assert applied.copy_location_text == "Bucharest, Romania"
    assert applied.copy_description == DESCRIPTION
    assert applied.copy_url is None
    assert applied.copied_at == applications.state_changed_at(applied)
    assert applications.posting_changed_since_copy(applied) is False


async def test_the_posting_copy_never_changes_after_later_moves_or_posting_edits(
    runtime: Runtime, settings: Settings, posting_id: int
) -> None:
    application = await start(runtime, posting_id)
    copied_at = (await move(runtime, application.id, "applied")).copied_at

    await edit_posting_text(settings, posting_id, title="Staff Data Engineer", description="New")
    for state in ("preparing", "screen_call", "applied", "offer"):
        moved = await move(runtime, application.id, state)

    assert moved.copied_at == copied_at
    assert moved.copy_title == "Data Engineer"
    assert moved.copy_description == DESCRIPTION
    assert applications.posting_changed_since_copy(moved) is True
    assert moved.job_posting.title == "Staff Data Engineer"


async def test_a_new_application_after_a_deletion_starts_clean(
    runtime: Runtime, posting_id: int
) -> None:
    first = await start(runtime, posting_id)
    await move(runtime, first.id, "applied")
    await move(runtime, first.id, "preparing")
    await delete(runtime, first.id)
    await set_triage(runtime, posting_id, "ignored")

    second = await start(runtime, posting_id)

    assert second.id != first.id
    assert [change.state for change in second.history] == ["preparing"]
    assert second.copied_at is None
    assert await triage_value(runtime, posting_id) == "interested"
    found = await read_posting(runtime, posting_id)
    assert found.application is not None and found.application.id == second.id


async def test_applications_in_the_same_state_are_listed_latest_move_first(
    runtime: Runtime, client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    first = await start(runtime, await add_posting(client, fake_llm, run_queued_tasks, "First"))
    second = await start(runtime, await add_posting(client, fake_llm, run_queued_tasks, "Second"))

    async def listed() -> list[int]:
        async with runtime.sessions() as session:
            return [a.id for a in await applications.by_state(session, owner_id=LOCAL_USER_ID)]

    await move(runtime, first.id, "applied")
    await move(runtime, second.id, "applied")
    assert await listed() == [second.id, first.id]

    await move(runtime, first.id, "preparing")
    await move(runtime, first.id, "applied")
    assert await listed() == [first.id, second.id]
