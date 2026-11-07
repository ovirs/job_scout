"""When a posting is evaluated again: re-run all unacted postings, and the update path for
a posting's text, which applies the rule for a changed posting."""

from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
import pytest
from test_applications import start, started_application
from test_evaluations import DESCRIPTION, write_career_profile
from test_triage import add_posting, titles, triage

from job_scout.config import Settings
from job_scout.job_postings.models import JobPosting
from job_scout.llm.fake import FakeLlm
from job_scout.posting_view import domain as posting_view
from job_scout.posting_view.schemas import JobPostingRead
from job_scout.reevaluation import domain as reevaluation
from job_scout.runtime import Runtime, open_runtime

RunTasks = Callable[[], Awaitable[None]]
QueuedTasks = Callable[[], Awaitable[list[str]]]


@pytest.fixture
async def runtime(settings: Settings) -> AsyncIterator[Runtime]:
    async with open_runtime(settings) as runtime:
        yield runtime


async def evaluation_count(client: httpx.AsyncClient, posting_id: int) -> int:
    return len((await client.get(f"/api/job-postings/{posting_id}/evaluations")).json())


async def rerun_all(client: httpx.AsyncClient) -> int:
    response = await client.post("/api/job-postings/rerun-evaluations")
    assert response.status_code == 201
    queued: int = response.json()["queued"]
    return queued


async def update_text(
    runtime: Runtime,
    posting_id: int,
    *,
    title: str | None = None,
    description: str = DESCRIPTION,
) -> bool:
    """Change the posting's text through its update path (Pipelines will use it); whether
    that queued an Evaluation."""
    async with runtime.sessions() as session:
        found = await session.get_one(JobPosting, posting_id)
        run = await reevaluation.update_text(
            session,
            runtime.task_queue,
            found,
            title=title or found.title,
            location_text=found.location_text,
            description=description,
        )
    return run is not None


async def read_posting(runtime: Runtime, posting_id: int) -> JobPostingRead:
    async with runtime.sessions() as session:
        found = await session.get_one(JobPosting, posting_id)
        return await posting_view.read(session, found)


async def test_rerun_all_queues_an_evaluation_for_each_open_untriaged_posting_and_no_others(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    ids = {
        title: await add_posting(client, fake_llm, run_queued_tasks, title)
        for title in ["Untriaged", "Another", "Interested", "Maybe", "Ignored", "Closed"]
    }
    await triage(client, ids["Interested"], "interested")
    await triage(client, ids["Maybe"], "maybe")
    await triage(client, ids["Ignored"], "ignored")
    await client.post(f"/api/job-postings/{ids['Closed']}/close")

    assert await rerun_all(client) == 2
    await run_queued_tasks()

    counts = {title: await evaluation_count(client, id) for title, id in ids.items()}
    assert counts == {
        "Untriaged": 2,
        "Another": 2,
        "Interested": 1,
        "Maybe": 1,
        "Ignored": 1,
        "Closed": 1,
    }


async def test_rerun_all_skips_a_posting_with_a_live_application(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks)

    assert await rerun_all(client) == 0
    await run_queued_tasks()

    assert await evaluation_count(client, application["job_posting_id"]) == 1


async def test_rerun_all_leaves_a_posting_whose_evaluation_is_under_way_to_it(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    queued_tasks: QueuedTasks,
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Waiting")

    assert await rerun_all(client) == 1
    assert await rerun_all(client) == 0

    assert await queued_tasks() == ["evaluate"]
    await run_queued_tasks()
    assert await evaluation_count(client, posting_id) == 2


async def test_rerun_all_with_nothing_to_run_queues_nothing(
    client: httpx.AsyncClient, queued_tasks: QueuedTasks
) -> None:
    assert await rerun_all(client) == 0
    assert await queued_tasks() == []


async def test_rerun_all_evaluates_with_the_current_user_inputs(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client, "Ten years of Python.")
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Data Engineer")
    second = await write_career_profile(client, "Fifteen years of Python.")

    await rerun_all(client)
    await run_queued_tasks()

    current = (await client.get(f"/api/job-postings/{posting_id}/evaluations/current")).json()
    assert current["career_profile_version_id"] == second


async def test_a_text_change_on_an_untriaged_posting_queues_a_new_evaluation(
    runtime: Runtime,
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    queued_tasks: QueuedTasks,
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Data Engineer")

    assert await update_text(runtime, posting_id, title="Staff Data Engineer")

    assert await queued_tasks() == ["evaluate"]
    await run_queued_tasks()
    assert await evaluation_count(client, posting_id) == 2
    found = await read_posting(runtime, posting_id)
    assert found.evaluation is not None and not found.evaluation.outdated


async def test_a_text_change_on_a_triaged_posting_outdates_its_evaluation_and_queues_nothing(
    runtime: Runtime,
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    queued_tasks: QueuedTasks,
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Data Engineer")
    await triage(client, posting_id, "maybe")

    assert not await update_text(runtime, posting_id, description=DESCRIPTION + " More.")

    assert await queued_tasks() == []
    assert await evaluation_count(client, posting_id) == 1
    found = await read_posting(runtime, posting_id)
    assert found.evaluation is not None and found.evaluation.outdated
    current = (await client.get(f"/api/job-postings/{posting_id}/evaluations/current")).json()
    assert current["outdated"] is True


async def test_a_text_change_on_a_posting_with_a_live_application_outdates_its_evaluation(
    runtime: Runtime, client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Data Engineer")
    assert (await start(client, posting_id)).status_code == 201
    await run_queued_tasks()

    assert not await update_text(runtime, posting_id, title="Staff Data Engineer")
    await run_queued_tasks()

    assert await evaluation_count(client, posting_id) == 1
    found = await read_posting(runtime, posting_id)
    assert found.evaluation is not None and found.evaluation.outdated


async def test_an_outdated_evaluation_is_replaced_by_rerunning_it(
    runtime: Runtime, client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Data Engineer")
    await triage(client, posting_id, "interested")
    await update_text(runtime, posting_id, description=DESCRIPTION + " More.")

    await client.post(f"/api/job-postings/{posting_id}/evaluations")
    await run_queued_tasks()

    found = await read_posting(runtime, posting_id)
    assert found.evaluation is not None and not found.evaluation.outdated


async def test_text_that_comes_out_the_same_queues_nothing(
    runtime: Runtime,
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    queued_tasks: QueuedTasks,
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Data Engineer")

    assert not await update_text(runtime, posting_id)

    assert await queued_tasks() == []
    found = await read_posting(runtime, posting_id)
    assert found.evaluation is not None and not found.evaluation.outdated


async def test_a_change_to_dates_or_metadata_queues_nothing_and_outdates_nothing(
    runtime: Runtime,
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    queued_tasks: QueuedTasks,
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Data Engineer")
    async with runtime.sessions() as session:
        found = await session.get_one(JobPosting, posting_id)
        found.company = "Acme Ltd"
        found.url = "https://example.com/jobs/1"
        found.workplace_type = "remote"
        found.last_seen_at = found.created_at.replace(year=2030)
        await session.commit()

    # The same text, as a Pipeline refreshing the posting would send it
    assert not await update_text(runtime, posting_id)

    assert await queued_tasks() == []
    refreshed = await read_posting(runtime, posting_id)
    assert refreshed.evaluation is not None and not refreshed.evaluation.outdated


async def test_a_text_change_while_an_evaluation_is_under_way_queues_no_second_one(
    runtime: Runtime,
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    queued_tasks: QueuedTasks,
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(
        client, fake_llm, run_queued_tasks, "Data Engineer", evaluate=False
    )

    assert not await update_text(runtime, posting_id, description=DESCRIPTION + " More.")

    assert await queued_tasks() == ["evaluate"]
    await run_queued_tasks()
    assert await evaluation_count(client, posting_id) == 1
    found = await read_posting(runtime, posting_id)
    assert found.evaluation is not None and not found.evaluation.outdated


async def test_a_changed_untriaged_posting_stays_in_the_inbox_while_its_new_evaluation_runs(
    runtime: Runtime, client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Data Engineer")

    await update_text(runtime, posting_id, description=DESCRIPTION + " More.")

    assert await titles(client, "inbox") == ["Data Engineer"]
