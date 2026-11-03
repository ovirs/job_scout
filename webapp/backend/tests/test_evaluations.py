from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from clipping_helpers import an_extraction, save_manual_entry

from job_scout.config import Settings
from job_scout.evaluations.prompt import EvaluationResult
from job_scout.llm import Failure
from job_scout.llm.fake import FakeLlm

DESCRIPTION = """About the job
We are building the data platform behind Acme's payments.
• You will design batch and streaming pipelines in Python.
- The team works “remote-first” from anywhere in Romania.
Spark experience is a nice to have.
Salary: 90,000 to 110,000 EUR a year."""


def a_result(**changes: object) -> EvaluationResult:
    fields: dict[str, object] = {
        "deal_breaker_verdicts": [],
        "red_flags": [],
        "green_flags": [
            {
                "point": "Python pipelines are the core of their experience.",
                "evidence": ["You will design batch and streaming pipelines in Python."],
            }
        ],
        "score": 7,
        "recommendation": "apply",
        "summary": "A senior data engineering role on a payments platform.",
    }
    return EvaluationResult.model_validate({**fields, **changes})


async def write_career_profile(
    client: httpx.AsyncClient, text: str = "Ten years of Python."
) -> int:
    saved = await client.post("/api/documents/career-profile/versions", json={"text": text})
    version_id: int = saved.json()["id"]
    return version_id


async def evaluated_posting(
    client: httpx.AsyncClient, run_queued_tasks: Callable[[], Awaitable[None]]
) -> dict[str, Any]:
    """Save a Manual Entry with `DESCRIPTION` and run its Evaluation; returns the posting."""
    posting = await save_manual_entry(client, run_queued_tasks, description=DESCRIPTION)
    await run_queued_tasks()
    found: dict[str, Any] = (await client.get(f"/api/job-postings/{posting['id']}")).json()
    return found


async def current_evaluation(client: httpx.AsyncClient, posting_id: int) -> dict[str, Any]:
    evaluation: dict[str, Any] = (
        await client.get(f"/api/job-postings/{posting_id}/evaluations/current")
    ).json()
    return evaluation


async def test_saving_a_confirmed_entry_produces_a_done_evaluation(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    await write_career_profile(client)
    fake_llm.evaluation.respond_with(a_result())

    saved = await save_manual_entry(client, run_queued_tasks, description=DESCRIPTION)
    assert saved["evaluation_status"] == "queued"
    await run_queued_tasks()

    posting = (await client.get(f"/api/job-postings/{saved['id']}")).json()
    assert posting["evaluation_status"] == "done"
    evaluation = await current_evaluation(client, saved["id"])
    assert evaluation["status"] == "done"
    assert evaluation["failure"] is None
    assert evaluation["score"] == 7
    assert evaluation["recommendation"] == "apply"
    assert evaluation["llm_recommendation"] == "apply"
    assert evaluation["disqualified_but_recommended"] is False
    assert evaluation["summary"] == "A senior data engineering role on a payments platform."
    assert evaluation["finished_at"] is not None
    assert len(fake_llm.evaluation.calls) == 1


@pytest.mark.parametrize(
    ("evidence", "starts_with", "ends_with"),
    [
        # Case and whitespace, including a line break in the quote
        (
            "you will design   BATCH and\nstreaming pipelines in python.",
            "You will design",
            "in Python.",
        ),
        # Straight quotes for the posting's curly ones
        ('works "remote-first" from', "works “remote-first”", "from"),
        # Across two bulleted lines, the bullets dropped
        ("pipelines in Python. The team works", "pipelines in Python.", "The team works"),
        # The quote keeps a bullet the posting has
        ("- The team works", "The team works", "The team works"),
        ("• You will design", "You will design", "You will design"),
    ],
)
async def test_a_quote_matches_the_posting_ignoring_whitespace_case_quote_styles_and_bullets(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
    evidence: str,
    starts_with: str,
    ends_with: str,
) -> None:
    await write_career_profile(client)
    fake_llm.evaluation.respond_with(
        a_result(red_flags=[{"point": "Worth a look.", "evidence": [evidence]}])
    )

    posting = await evaluated_posting(client, run_queued_tasks)

    evaluation = await current_evaluation(client, posting["id"])
    start = DESCRIPTION.index(starts_with)
    end = DESCRIPTION.index(ends_with, start) + len(ends_with)
    assert evaluation["red_flags"][0]["evidence"] == [evidence]
    assert evaluation["red_flags"][0]["evidence_matches"] == [
        {
            "field": "description",
            "start": start,
            "end": end,
        }
    ]


async def test_a_quote_from_the_title_matches_there(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    await write_career_profile(client)
    fake_llm.evaluation.respond_with(
        a_result(green_flags=[{"point": "The level they want.", "evidence": ["senior data"]}])
    )

    posting = await evaluated_posting(client, run_queued_tasks)

    evaluation = await current_evaluation(client, posting["id"])
    assert evaluation["green_flags"][0]["evidence_matches"] == [
        {
            "field": "title",
            "start": 0,
            "end": len("Senior Data"),
        }
    ]


async def add_deal_breaker(client: httpx.AsyncClient, text: str) -> int:
    """Add a Deal Breaker; returns its id."""
    deal_breakers = (await client.post("/api/deal-breakers", json={"text": text})).json()
    deal_breaker_id: int = deal_breakers["deal_breakers"][-1]["id"]
    return deal_breaker_id


def a_verdict(
    deal_breaker_id: int, verdict: str = "unknown", **changes: object
) -> dict[str, object]:
    return {
        "deal_breaker_id": deal_breaker_id,
        "verdict": verdict,
        "evidence": [],
        "explanation": "The posting does not say.",
        **changes,
    }


A_FLAG = {"point": "Payments matter to them.", "evidence": ["Acme's payments"]}
SPARK = "Spark is a required skill."
ROMANIA = "Fully remote from Romania."


@pytest.mark.parametrize(
    ("evidence", "field", "value"),
    [
        ("Title: Senior Data Engineer", "title", "Senior Data Engineer"),
        ("Company: Acme", "company", "Acme"),
        ("location:  bucharest, romania", "location_text", "Bucharest, Romania"),
        ("Description: About the job", "description", "About the job"),
    ],
)
async def test_a_quote_with_the_label_the_prompt_gives_its_field_matches_that_field(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
    evidence: str,
    field: str,
    value: str,
) -> None:
    await write_career_profile(client)
    fake_llm.evaluation.respond_with(
        a_result(green_flags=[{"point": "Where it is.", "evidence": [evidence]}])
    )

    posting = await evaluated_posting(client, run_queued_tasks)

    assert posting["evaluation_status"] == "done"
    evaluation = await current_evaluation(client, posting["id"])
    assert evaluation["green_flags"][0]["evidence"] == [evidence]
    # Highlights the value, not the label the posting does not contain
    assert evaluation["green_flags"][0]["evidence_matches"] == [
        {"field": field, "start": 0, "end": len(value)}
    ]


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        (
            {
                "red_flags": [
                    {
                        "point": "Hidden.",
                        "evidence": [A_FLAG["evidence"][0], "unpaid weekend on-call"],
                    }
                ]
            },
            "quotes words the posting does not contain: 'unpaid weekend on-call'",
        ),
        # A label only matches with its own field's text after it
        (
            {"red_flags": [{"point": "Mislabelled.", "evidence": ["Company: Senior Data"]}]},
            "quotes words the posting does not contain: 'Company: Senior Data'",
        ),
        ({"verdicts": "first only"}, "no verdict for Deal Breaker"),
        ({"verdicts": "first twice"}, "more than one verdict for Deal Breaker"),
        ({"verdicts": "unknown id"}, "a verdict for Deal Breaker 999, which"),
        ({"verdicts": "violated without evidence"}, "has no evidence"),
        ({"verdicts": "clear without evidence"}, "has no evidence"),
        ({"red_flags": [{"point": "Unfounded.", "evidence": []}]}, "red flag has no evidence"),
        ({"score": 11}, "score of 11 is not between 1 and 10"),
        ({"score": 0}, "score of 0 is not between 1 and 10"),
        ({"red_flags": [A_FLAG] * 6}, "6 red flags, more than 5"),
        ({"green_flags": [A_FLAG] * 6}, "6 green flags, more than 5"),
    ],
)
async def test_a_result_failing_a_check_ends_after_retries_as_not_evaluated_with_the_reason(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
    changes: dict[str, object],
    reason: str,
) -> None:
    await write_career_profile(client)
    spark = await add_deal_breaker(client, SPARK)
    romania = await add_deal_breaker(client, ROMANIA)
    verdicts = {
        "first only": [a_verdict(spark)],
        "first twice": [a_verdict(spark), a_verdict(spark), a_verdict(romania)],
        "unknown id": [a_verdict(spark), a_verdict(romania), a_verdict(999)],
        "violated without evidence": [a_verdict(spark, "violated"), a_verdict(romania)],
        "clear without evidence": [a_verdict(spark), a_verdict(romania, "clear")],
        None: [a_verdict(spark), a_verdict(romania)],
    }[changes.get("verdicts")]  # type: ignore[index]
    changes = {key: value for key, value in changes.items() if key != "verdicts"}
    fake_llm.evaluation.respond_with(a_result(deal_breaker_verdicts=verdicts, **changes))

    posting = await evaluated_posting(client, run_queued_tasks)

    assert posting["evaluation_status"] == "not_evaluated"
    assert len(fake_llm.evaluation.calls) == 3
    [evaluation] = (await client.get(f"/api/job-postings/{posting['id']}/evaluations")).json()
    assert evaluation["status"] == "not_evaluated"
    assert evaluation["failure"]["kind"] == "malformed"
    assert reason in evaluation["failure"]["reason"]
    assert evaluation["recommendation"] is None  # never counted as a skip
    assert evaluation["deal_breaker_verdicts"] == []
    assert await current_evaluation(client, posting["id"]) is None


async def test_a_result_failing_a_check_is_retried_and_a_good_one_is_kept(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    await write_career_profile(client)
    fake_llm.evaluation.respond_with(a_result(score=12), a_result(score=8))

    posting = await evaluated_posting(client, run_queued_tasks)

    assert posting["evaluation_status"] == "done"
    assert len(fake_llm.evaluation.calls) == 2
    assert (await current_evaluation(client, posting["id"]))["score"] == 8


@pytest.mark.parametrize(
    "failure",
    [Failure("error", "The Anthropic API is overloaded"), Failure("refusal", "Declined")],
)
async def test_a_failed_call_ends_after_retries_as_not_evaluated_with_the_reason(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
    failure: Failure,
) -> None:
    await write_career_profile(client)
    fake_llm.evaluation.respond_with(failure)

    posting = await evaluated_posting(client, run_queued_tasks)

    [evaluation] = (await client.get(f"/api/job-postings/{posting['id']}/evaluations")).json()
    assert evaluation["status"] == "not_evaluated"
    assert evaluation["failure"] == {"kind": failure.kind, "reason": failure.reason}
    assert evaluation["recommendation"] is None
    assert len(fake_llm.evaluation.calls) == 3


@pytest.mark.parametrize(
    ("llm_recommendation", "disqualified_but_recommended"),
    [("apply", True), ("maybe", True), ("skip", False)],
)
async def test_a_violated_deal_breaker_stores_skip_and_keeps_the_llms_recommendation(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
    llm_recommendation: str,
    disqualified_but_recommended: bool,
) -> None:
    await write_career_profile(client)
    spark = await add_deal_breaker(client, SPARK)
    romania = await add_deal_breaker(client, ROMANIA)
    violated = a_verdict(
        spark,
        "violated",
        evidence=["Spark experience is a nice to have."],
        explanation="Spark is asked for.",
    )
    clear = a_verdict(
        romania, "clear", evidence=["from anywhere in Romania"], explanation="Remote in Romania."
    )
    fake_llm.evaluation.respond_with(
        a_result(deal_breaker_verdicts=[violated, clear], recommendation=llm_recommendation)
    )

    posting = await evaluated_posting(client, run_queued_tasks)

    evaluation = await current_evaluation(client, posting["id"])
    assert evaluation["recommendation"] == "skip"
    assert evaluation["llm_recommendation"] == llm_recommendation
    assert evaluation["disqualified_but_recommended"] is disqualified_but_recommended
    assert evaluation["score"] == 7  # the score ignores Deal Breakers
    assert [
        (v["deal_breaker_id"], v["deal_breaker_text"], v["verdict"])
        for v in evaluation["deal_breaker_verdicts"]
    ] == [(spark, SPARK, "violated"), (romania, ROMANIA, "clear")]
    start = DESCRIPTION.index("Spark experience")
    assert evaluation["deal_breaker_verdicts"][0]["evidence_matches"] == [
        {
            "field": "description",
            "start": start,
            "end": start + len("Spark experience is a nice to have."),
        }
    ]
    assert evaluation["deal_breaker_verdicts"][0]["explanation"] == "Spark is asked for."
    assert evaluation["to_check"] == []


async def test_an_unknown_verdict_is_an_item_to_check_and_changes_nothing_else(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    await write_career_profile(client)
    spark = await add_deal_breaker(client, SPARK)
    romania = await add_deal_breaker(client, ROMANIA)
    unknown = a_verdict(spark, explanation="Ask whether Spark is used day to day.")
    clear = a_verdict(romania, "clear", evidence=["anywhere in Romania"])
    fake_llm.evaluation.respond_with(
        a_result(deal_breaker_verdicts=[unknown, clear], recommendation="apply")
    )

    posting = await evaluated_posting(client, run_queued_tasks)

    evaluation = await current_evaluation(client, posting["id"])
    assert evaluation["recommendation"] == "apply"
    assert evaluation["llm_recommendation"] == "apply"
    assert evaluation["disqualified_but_recommended"] is False
    assert evaluation["to_check"] == [
        {
            "deal_breaker_id": spark,
            "deal_breaker_text": SPARK,
            "verdict": "unknown",
            "evidence": [],
            "evidence_matches": [],
            "explanation": "Ask whether Spark is used day to day.",
        }
    ]


async def test_rerunning_a_posting_adds_an_evaluation_and_keeps_the_earlier_ones_as_history(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    settings: Settings,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    first_profile = await write_career_profile(client, "Ten years of Python.")
    preferences = (
        await client.post("/api/documents/preferences/versions", json={"text": "Senior roles."})
    ).json()["id"]
    spark = await add_deal_breaker(client, SPARK)
    first_set = (await client.get("/api/deal-breakers")).json()["id"]
    fake_llm.evaluation.respond_with(a_result(deal_breaker_verdicts=[a_verdict(spark)], score=6))
    posting = await evaluated_posting(client, run_queued_tasks)
    # Rewording an input re-runs nothing by itself
    second_profile = await write_career_profile(client, "Ten years of Python and Spark.")
    await client.put(f"/api/deal-breakers/{spark}", json={"text": "Spark is required."})
    second_set = (await client.get("/api/deal-breakers")).json()["id"]
    await run_queued_tasks()
    assert len(fake_llm.evaluation.calls) == 1
    fake_llm.evaluation.respond_with(a_result(deal_breaker_verdicts=[a_verdict(spark)], score=9))

    rerun = await client.post(f"/api/job-postings/{posting['id']}/evaluations")

    assert rerun.status_code == 201
    assert rerun.json()["status"] == "queued"
    assert (await client.get(f"/api/job-postings/{posting['id']}")).json()[
        "evaluation_status"
    ] == "queued"
    # The earlier one stays current until the new one is done
    assert (await current_evaluation(client, posting["id"]))["score"] == 6
    await run_queued_tasks()

    history = (await client.get(f"/api/job-postings/{posting['id']}/evaluations")).json()
    assert [e["score"] for e in history] == [9, 6]  # the latest first
    assert history[0]["id"] == rerun.json()["id"]
    assert [
        (
            e["model"],
            e["prompt_version"],
            e["career_profile_version_id"],
            e["preferences_version_id"],
            e["deal_breaker_set_version_id"],
            e["outdated"],
        )
        for e in history
    ] == [
        (settings.evaluation_model, "v2", second_profile, preferences, second_set, False),
        (settings.evaluation_model, "v2", first_profile, preferences, first_set, False),
    ]
    # Numbered as the user sees the versions on the pages that edit them
    assert [
        (
            e["career_profile_version_number"],
            e["preferences_version_number"],
            e["deal_breaker_set_version_number"],
        )
        for e in history
    ] == [(2, 1, 2), (1, 1, 1)]
    # Each judged against the Deal Breakers as they were worded then
    assert [e["deal_breaker_verdicts"][0]["deal_breaker_text"] for e in history] == [
        "Spark is required.",
        SPARK,
    ]
    assert (await current_evaluation(client, posting["id"]))["id"] == rerun.json()["id"]


async def test_a_posting_not_evaluated_waits_for_a_manual_retry(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    await write_career_profile(client)
    fake_llm.evaluation.respond_with(Failure("error", "The Anthropic API is overloaded"))
    posting = await evaluated_posting(client, run_queued_tasks)
    await run_queued_tasks()
    assert len(fake_llm.evaluation.calls) == 3  # nothing left on the queue
    fake_llm.evaluation.respond_with(a_result())

    retried = await client.post(f"/api/job-postings/{posting['id']}/evaluations")
    await run_queued_tasks()

    assert retried.status_code == 201
    history = (await client.get(f"/api/job-postings/{posting['id']}/evaluations")).json()
    assert [e["status"] for e in history] == ["done", "not_evaluated"]
    assert (await client.get(f"/api/job-postings/{posting['id']}")).json()[
        "evaluation_status"
    ] == "done"


async def test_a_posting_can_be_rerun_while_its_evaluation_is_under_way(
    client: httpx.AsyncClient, run_queued_tasks: Callable[[], Awaitable[None]]
) -> None:
    await write_career_profile(client)
    posting = await save_manual_entry(client, run_queued_tasks)

    rerun = await client.post(f"/api/job-postings/{posting['id']}/evaluations")
    await run_queued_tasks()

    assert rerun.status_code == 201
    history = (await client.get(f"/api/job-postings/{posting['id']}/evaluations")).json()
    assert [e["status"] for e in history] == ["done", "done"]


async def test_an_unknown_posting_has_no_evaluations_and_cannot_be_rerun(
    client: httpx.AsyncClient,
) -> None:
    assert (await client.get("/api/job-postings/1/evaluations")).status_code == 404
    assert (await client.get("/api/job-postings/1/evaluations/current")).status_code == 404
    assert (await client.post("/api/job-postings/1/evaluations")).status_code == 404


async def test_the_prompt_sends_the_users_inputs_first_and_the_posting_last_without_its_facts(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    await write_career_profile(client, "Ten years of Python at Initech.")
    await client.post("/api/documents/preferences/versions", json={"text": "Payments, please."})
    spark = await add_deal_breaker(client, SPARK)
    romania = await add_deal_breaker(client, ROMANIA)
    fake_llm.manual_entry_extraction.respond_with(
        an_extraction(
            salary_ranges=[
                {
                    "minimum": 123456,
                    "maximum": None,
                    "currency": "CHF",
                    "period": "year",
                    "applies_to": "Zurich",
                }
            ],
            location_restriction="Only within the EU",
            required_technologies=[{"name": "Kubernetes", "alternative_group": None}],
            nice_to_have_technologies=[{"name": "Haskell", "alternative_group": None}],
        )
    )
    fake_llm.evaluation.respond_with(
        a_result(deal_breaker_verdicts=[a_verdict(spark), a_verdict(romania)])
    )

    await evaluated_posting(client, run_queued_tasks)

    [prompt] = fake_llm.evaluation.calls
    user_inputs, posting = prompt.blocks
    assert "Ten years of Python at Initech." in user_inputs
    assert "Payments, please." in user_inputs
    assert f"[{spark}] {SPARK}" in user_inputs
    assert f"[{romania}] {ROMANIA}" in user_inputs
    assert DESCRIPTION not in user_inputs
    assert "Senior Data Engineer" in posting
    assert "Acme" in posting
    assert "Bucharest, Romania" in posting
    assert DESCRIPTION in posting
    assert "Ten years of Python" not in posting
    assert "hybrid" not in posting.lower()  # the workplace type is an extracted fact too
    for extracted_only in [
        "123456",
        "CHF",
        "Zurich",
        "Only within the EU",
        "Kubernetes",
        "Haskell",
    ]:
        assert all(extracted_only not in block for block in prompt.blocks)


async def test_without_a_career_profile_the_posting_is_not_evaluated_and_no_llm_is_called(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    await write_career_profile(client, "  \n")  # cleared

    posting = await evaluated_posting(client, run_queued_tasks)

    assert posting["evaluation_status"] == "not_evaluated"
    [evaluation] = (await client.get(f"/api/job-postings/{posting['id']}/evaluations")).json()
    assert evaluation["failure"]["kind"] == "missing_input"
    assert "Career Profile" in evaluation["failure"]["reason"]
    assert fake_llm.evaluation.calls == []

    await write_career_profile(client)
    await client.post(f"/api/job-postings/{posting['id']}/evaluations")
    await run_queued_tasks()

    assert (await client.get(f"/api/job-postings/{posting['id']}")).json()[
        "evaluation_status"
    ] == "done"


async def test_without_deal_breakers_or_preferences_the_evaluation_has_no_verdicts(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    await write_career_profile(client)
    # A Deal Breaker deleted again leaves none
    await client.delete(f"/api/deal-breakers/{await add_deal_breaker(client, SPARK)}")
    fake_llm.evaluation.respond_with(a_result(deal_breaker_verdicts=[]))

    posting = await evaluated_posting(client, run_queued_tasks)

    evaluation = await current_evaluation(client, posting["id"])
    assert evaluation["deal_breaker_verdicts"] == []
    assert evaluation["recommendation"] == "apply"
    assert evaluation["preferences_version_id"] is None
    [prompt] = fake_llm.evaluation.calls
    assert "no Deal Breakers" in prompt.user_inputs
    assert "no Preferences" in prompt.user_inputs
    assert SPARK not in prompt.user_inputs


async def test_an_unexpected_error_ends_after_retries_as_not_evaluated(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    await write_career_profile(client)
    fake_llm.evaluation.respond_with(RuntimeError("boom"))

    posting = await evaluated_posting(client, run_queued_tasks)

    [evaluation] = (await client.get(f"/api/job-postings/{posting['id']}/evaluations")).json()
    assert evaluation["status"] == "not_evaluated"
    assert evaluation["failure"]["kind"] == "error"
    assert "boom" in evaluation["failure"]["reason"]
    assert len(fake_llm.evaluation.calls) == 3


async def test_a_verdict_resting_on_several_passages_has_each_one_found(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    await write_career_profile(client)
    spark = await add_deal_breaker(client, SPARK)
    passages = ["Spark experience is a nice to have.", "pipelines in Python"]
    fake_llm.evaluation.respond_with(
        a_result(deal_breaker_verdicts=[a_verdict(spark, "clear", evidence=passages)])
    )

    posting = await evaluated_posting(client, run_queued_tasks)

    [verdict] = (await current_evaluation(client, posting["id"]))["deal_breaker_verdicts"]
    assert verdict["evidence"] == passages
    assert [(m["start"], m["end"]) for m in verdict["evidence_matches"]] == [
        (DESCRIPTION.index(p), DESCRIPTION.index(p) + len(p)) for p in passages
    ]
