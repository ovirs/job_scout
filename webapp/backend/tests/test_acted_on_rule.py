"""The acted-on rule: a posting with any Triage or a live Application is acted on, and its
Evaluation is no longer re-run by a bulk re-run or by a change to the posting's text."""

from collections.abc import Awaitable, Callable
from datetime import datetime

import httpx
import pytest
from test_applications import delete, edit_posting_text, posting, start
from test_evaluations import DESCRIPTION, a_result, current_evaluation, write_career_profile
from test_triage import add_posting, triage

from job_scout.config import Settings
from job_scout.llm.fake import FakeLlm

RunTasks = Callable[[], Awaitable[None]]
QueuedTasks = Callable[[], Awaitable[list[str]]]


async def rerun_unacted(client: httpx.AsyncClient) -> httpx.Response:
    return await client.post("/api/evaluations/rerun-unacted")


async def scores(client: httpx.AsyncClient, posting_id: int) -> list[int | None]:
    """The score of each of the posting's Evaluations, the latest first."""
    history = (await client.get(f"/api/job-postings/{posting_id}/evaluations")).json()
    return [evaluation["score"] for evaluation in history]


async def test_rerunning_all_unacted_queues_one_for_each_open_untriaged_posting_only(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    untriaged = await add_posting(client, fake_llm, run_queued_tasks, "Untriaged")
    maybe = await add_posting(client, fake_llm, run_queued_tasks, "Maybe")
    await triage(client, maybe, "maybe")
    applying = await add_posting(client, fake_llm, run_queued_tasks, "Applying")
    await start(client, applying)
    closed = await add_posting(client, fake_llm, run_queued_tasks, "Closed")
    await client.post(f"/api/job-postings/{closed}/close")
    fake_llm.evaluation.respond_with(a_result(score=9))

    rerun = await rerun_unacted(client)
    await run_queued_tasks()

    assert rerun.status_code == 201
    assert [(e["job_posting_id"], e["status"]) for e in rerun.json()] == [(untriaged, "queued")]
    assert await scores(client, untriaged) == [9, 7]
    assert await scores(client, maybe) == [7]
    assert await scores(client, applying) == [7]
    assert await scores(client, closed) == [7]


async def test_a_text_change_on_an_untriaged_posting_queues_a_new_evaluation(
    client: httpx.AsyncClient,
    settings: Settings,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    queued_tasks: QueuedTasks,
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Data Engineer")

    await edit_posting_text(settings, posting_id, description=DESCRIPTION + "\nSpark is required.")

    assert await queued_tasks() == ["evaluate"]
    assert (await posting(client, posting_id))["evaluation"]["outdated"] is True
    fake_llm.evaluation.respond_with(a_result(score=9))
    await run_queued_tasks()
    assert await scores(client, posting_id) == [9, 7]
    assert (await current_evaluation(client, posting_id))["outdated"] is False
    assert "Spark is required." in fake_llm.evaluation.calls[-1].posting


async def triaged_maybe(client: httpx.AsyncClient, posting_id: int) -> None:
    assert (await triage(client, posting_id, "maybe")).status_code == 200


async def applying(client: httpx.AsyncClient, posting_id: int) -> None:
    assert (await start(client, posting_id)).status_code == 201


async def applied_and_deleted(client: httpx.AsyncClient, posting_id: int) -> None:
    """A deleted Application leaves the Triage at Interested, so still acted on."""
    application = (await start(client, posting_id)).json()
    assert (await delete(client, application["id"])).status_code == 204


@pytest.mark.parametrize("act", [triaged_maybe, applying, applied_and_deleted])
async def test_a_text_change_on_an_acted_on_posting_keeps_its_evaluation_marked_outdated(
    client: httpx.AsyncClient,
    settings: Settings,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    queued_tasks: QueuedTasks,
    act: Callable[[httpx.AsyncClient, int], Awaitable[None]],
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Data Engineer")
    await act(client, posting_id)

    await edit_posting_text(settings, posting_id, title="Staff Data Engineer")

    assert await queued_tasks() == []
    assert await scores(client, posting_id) == [7]
    found = await posting(client, posting_id)
    assert found["title"] == "Staff Data Engineer"
    # What the "edited since you triaged it" badge shows from
    assert found["triage"] is not None
    assert found["evaluation"]["outdated"] is True
    assert (await current_evaluation(client, posting_id))["outdated"] is True


async def test_a_change_to_dates_or_metadata_queues_nothing(
    client: httpx.AsyncClient,
    settings: Settings,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    queued_tasks: QueuedTasks,
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Data Engineer")
    await client.post(f"/api/job-postings/{posting_id}/close")
    await client.post(f"/api/job-postings/{posting_id}/reopen")

    await edit_posting_text(
        settings,
        posting_id,
        metadata={
            "company": "Acme Payments",
            "url": "https://example.com/jobs/1",
            "workplace_type": "remote",
            "last_seen_at": datetime(2026, 11, 1),
        },
    )

    assert await queued_tasks() == []
    assert await scores(client, posting_id) == [7]
    found = await posting(client, posting_id)
    assert found["company"] == "Acme Payments"
    assert found["evaluation"]["outdated"] is False


async def test_a_text_change_while_an_evaluation_is_under_way_leaves_it_to_that_one(
    client: httpx.AsyncClient,
    settings: Settings,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    queued_tasks: QueuedTasks,
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(
        client, fake_llm, run_queued_tasks, "Data Engineer", evaluate=False
    )

    await edit_posting_text(
        settings, posting_id, description=DESCRIPTION + "\nLead the data platform team."
    )
    rerun = await rerun_unacted(client)

    assert rerun.status_code == 201
    assert rerun.json() == []
    assert await queued_tasks() == ["evaluate"]
    await run_queued_tasks()
    # The queued one read the posting when it started, so it judged the new text
    assert "Lead the data platform team." in fake_llm.evaluation.calls[-1].posting
    assert (await current_evaluation(client, posting_id))["outdated"] is False
