from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from clipping_helpers import save_manual_entry
from test_evaluations import (
    DESCRIPTION,
    SPARK,
    a_result,
    a_verdict,
    add_deal_breaker,
    write_career_profile,
)

from job_scout.llm import Failure
from job_scout.llm.fake import FakeLlm

RunTasks = Callable[[], Awaitable[None]]


async def add_posting(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    title: str,
    *,
    evaluate: bool = True,
    result: Any = None,
) -> int:
    """Save a Manual Entry titled `title`; with `evaluate`, run its Evaluation with `result`."""
    fake_llm.evaluation.respond_with(result or a_result())
    posting = await save_manual_entry(
        client, run_queued_tasks, title=title, description=DESCRIPTION
    )
    if evaluate:
        await run_queued_tasks()
    posting_id: int = posting["id"]
    return posting_id


async def titles(client: httpx.AsyncClient, list_name: str, **params: str) -> list[str]:
    response = await client.get("/api/job-postings", params={"list": list_name, **params})
    assert response.status_code == 200
    return [row["title"] for row in response.json()]


async def triage(client: httpx.AsyncClient, posting_id: int, value: str) -> httpx.Response:
    return await client.put(f"/api/job-postings/{posting_id}/triage", json={"value": value})


async def test_the_inbox_holds_untriaged_apply_and_maybe_postings_by_score_descending(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    for title, score, recommendation in [
        ("Middling", 5, "maybe"),
        ("Best", 9, "apply"),
        ("Skipped", 8, "skip"),
        ("Good", 7, "apply"),
    ]:
        await add_posting(
            client,
            fake_llm,
            run_queued_tasks,
            title,
            result=a_result(score=score, recommendation=recommendation),
        )

    assert await titles(client, "inbox") == ["Best", "Good", "Middling"]
    assert await titles(client, "skip") == ["Skipped"]


async def test_the_inbox_can_be_sorted_by_age_newest_first(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    for title, score in [("Old high", 9), ("New low", 3)]:
        await add_posting(client, fake_llm, run_queued_tasks, title, result=a_result(score=score))

    assert await titles(client, "inbox", sort="age") == ["New low", "Old high"]


async def test_inbox_rows_carry_the_evaluation_they_show(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    await add_posting(client, fake_llm, run_queued_tasks, "Row", result=a_result(score=8))

    [row] = (await client.get("/api/job-postings", params={"list": "inbox"})).json()

    assert row["company"] == "Acme"
    assert row["created_at"] is not None
    assert row["triage"] is None
    evaluation = row["evaluation"]
    assert evaluation["score"] == 8
    assert evaluation["recommendation"] == "apply"
    assert evaluation["summary"] == "A senior data engineering role on a payments platform."
    assert evaluation["disqualified_but_recommended"] is False
    assert evaluation["outdated"] is False


async def test_a_disqualified_but_recommended_posting_is_in_the_inbox_with_its_badge(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    spark = await add_deal_breaker(client, SPARK)
    violated = a_verdict(
        spark,
        "violated",
        evidence=["Spark experience is a nice to have."],
        explanation="Spark is asked for.",
    )
    await add_posting(
        client,
        fake_llm,
        run_queued_tasks,
        "Tempting",
        result=a_result(deal_breaker_verdicts=[violated], recommendation="apply"),
    )
    await add_posting(
        client,
        fake_llm,
        run_queued_tasks,
        "Clear skip",
        result=a_result(deal_breaker_verdicts=[violated], recommendation="skip"),
    )

    assert await titles(client, "inbox") == ["Tempting"]
    assert await titles(client, "skip") == ["Clear skip"]
    [row] = (await client.get("/api/job-postings", params={"list": "inbox"})).json()
    assert row["evaluation"]["recommendation"] == "skip"
    assert row["evaluation"]["llm_recommendation"] == "apply"
    assert row["evaluation"]["disqualified_but_recommended"] is True
    assert row["evaluation"]["violated_deal_breakers"] == [
        {
            "deal_breaker_id": spark,
            "deal_breaker_text": SPARK,
            "evidence": ["Spark experience is a nice to have."],
        }
    ]


async def test_a_failed_evaluation_is_in_not_evaluated_and_never_in_skip(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    await add_posting(
        client,
        fake_llm,
        run_queued_tasks,
        "Broken",
        result=Failure("error", "The Anthropic API is overloaded"),
    )

    assert await titles(client, "not-evaluated") == ["Broken"]
    assert await titles(client, "skip") == []
    assert await titles(client, "inbox") == []
    [row] = (await client.get("/api/job-postings", params={"list": "not-evaluated"})).json()
    assert row["evaluation_status"] == "failed"
    assert row["evaluation_failure"] == {
        "kind": "error",
        "reason": "The Anthropic API is overloaded",
    }
    assert row["evaluation"] is None


async def test_a_posting_awaiting_its_evaluation_is_in_not_evaluated(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await add_posting(client, fake_llm, run_queued_tasks, "Waiting", evaluate=False)

    [row] = (await client.get("/api/job-postings", params={"list": "not-evaluated"})).json()
    assert row["title"] == "Waiting"
    assert row["evaluation_status"] == "queued"
    assert row["evaluation_failure"] is None


async def test_a_posting_with_an_earlier_done_evaluation_stays_listed_by_it_while_rerun(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Rerun")
    await client.post(f"/api/job-postings/{posting_id}/evaluations")

    assert await titles(client, "inbox") == ["Rerun"]
    assert await titles(client, "not-evaluated") == []


async def test_a_posting_can_be_triaged_before_its_evaluation_finishes(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Early", evaluate=False)

    response = await triage(client, posting_id, "interested")

    assert response.status_code == 200
    assert response.json()["triage"]["value"] == "interested"
    assert await titles(client, "not-evaluated") == []
    assert await titles(client, "shortlist") == ["Early"]


async def test_a_posting_whose_evaluation_failed_can_be_triaged(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(
        client, fake_llm, run_queued_tasks, "Broken", result=Failure("error", "Overloaded")
    )

    assert (await triage(client, posting_id, "maybe")).status_code == 200
    assert await titles(client, "later") == ["Broken"]


@pytest.mark.parametrize(
    ("value", "list_name"),
    [("interested", "shortlist"), ("maybe", "later"), ("ignored", "ignored")],
)
async def test_triaging_moves_a_posting_out_of_the_inbox_and_into_its_list(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    value: str,
    list_name: str,
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Pick")
    await add_posting(client, fake_llm, run_queued_tasks, "Other")

    await triage(client, posting_id, value)

    assert await titles(client, "inbox") == ["Other"]
    assert await titles(client, list_name) == ["Pick"]


async def test_a_triaged_skip_is_out_of_the_skip_list(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(
        client, fake_llm, run_queued_tasks, "Skipped", result=a_result(recommendation="skip")
    )

    await triage(client, posting_id, "interested")

    assert await titles(client, "skip") == []
    assert await titles(client, "shortlist") == ["Skipped"]


async def test_the_triage_can_be_changed_and_records_who_set_it_and_when(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Fickle")

    first = (await triage(client, posting_id, "maybe")).json()["triage"]
    second = (await triage(client, posting_id, "interested")).json()["triage"]

    assert first["value"] == "maybe"
    assert first["origin"] == "user"
    assert second["value"] == "interested"
    assert second["origin"] == "user"
    assert second["created_at"] == first["created_at"]  # when it was first triaged
    assert second["changed_at"] >= first["changed_at"]
    assert await titles(client, "later") == []
    assert await titles(client, "shortlist") == ["Fickle"]
    posting = (await client.get(f"/api/job-postings/{posting_id}")).json()
    assert posting["triage"] == second


async def test_an_unknown_triage_value_is_rejected(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Odd", evaluate=False)

    assert (await triage(client, posting_id, "untriaged")).status_code == 422


async def test_triaging_an_unknown_posting_is_not_found(client: httpx.AsyncClient) -> None:
    assert (await triage(client, 999, "interested")).status_code == 404


async def test_closing_an_untriaged_posting_removes_it_from_inbox_skip_and_not_evaluated(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    in_inbox = await add_posting(client, fake_llm, run_queued_tasks, "Inbox")
    in_skip = await add_posting(
        client, fake_llm, run_queued_tasks, "Skip", result=a_result(recommendation="skip")
    )
    waiting = await add_posting(client, fake_llm, run_queued_tasks, "Waiting", evaluate=False)

    for posting_id in (in_inbox, in_skip, waiting):
        await client.post(f"/api/job-postings/{posting_id}/close")

    assert await titles(client, "inbox") == []
    assert await titles(client, "skip") == []
    assert await titles(client, "not-evaluated") == []

    await client.post(f"/api/job-postings/{in_inbox}/reopen")
    assert await titles(client, "inbox") == ["Inbox"]


async def test_closing_an_interested_posting_keeps_it_on_the_shortlist_with_its_closed_date(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(client, fake_llm, run_queued_tasks, "Gone")
    await triage(client, posting_id, "interested")

    closed = (await client.post(f"/api/job-postings/{posting_id}/close")).json()

    [row] = (await client.get("/api/job-postings", params={"list": "shortlist"})).json()
    assert row["title"] == "Gone"
    assert row["closed_at"] == closed["closed_at"] is not None


async def test_closed_postings_leave_later_and_ignored(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    maybe = await add_posting(client, fake_llm, run_queued_tasks, "Maybe")
    ignored = await add_posting(client, fake_llm, run_queued_tasks, "Ignored")
    await triage(client, maybe, "maybe")
    await triage(client, ignored, "ignored")

    for posting_id in (maybe, ignored):
        await client.post(f"/api/job-postings/{posting_id}/close")

    assert await titles(client, "later") == []
    assert await titles(client, "ignored") == []


async def test_triaged_lists_default_to_newest_first_and_can_sort_by_score(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    for title, score in [("High", 9), ("Low", 2), ("Mid", 5)]:
        posting_id = await add_posting(
            client, fake_llm, run_queued_tasks, title, result=a_result(score=score)
        )
        await triage(client, posting_id, "interested")
    unevaluated = await add_posting(client, fake_llm, run_queued_tasks, "None", evaluate=False)
    await triage(client, unevaluated, "interested")

    assert await titles(client, "shortlist") == ["None", "Mid", "Low", "High"]
    assert await titles(client, "shortlist", sort="score") == ["High", "Mid", "Low", "None"]


async def test_an_unknown_list_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/job-postings", params={"list": "nowhere"})
    assert response.status_code == 422
