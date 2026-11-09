"""The model choice of each run the user starts: given in the request, or the step's default
when omitted, or, for a Clipping retry, the choice the Clipping was read with."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from clipping_helpers import PASTED_TEXT, an_extraction, submit_and_extract
from conftest import TEST_KEY
from test_applications import started_application
from test_cover_letters import a_letter, generate
from test_evaluations import write_career_profile
from test_models import SONNET

from job_scout.llm import Failure
from job_scout.llm.fake import OPUS, FakeLlm, FakeModelLister
from job_scout.llm.interface import ModelChoice

RunTasks = Callable[[], Awaitable[None]]

SONNET_HIGH = {"provider": "anthropic", "model": "claude-sonnet-5", "effort": "high"}


@pytest.fixture
async def with_sonnet(client: httpx.AsyncClient, fake_lister: FakeModelLister) -> httpx.AsyncClient:
    """The `client`, with Claude Sonnet 5 offered beside the default, Claude Opus 5.5."""
    fake_lister.listings["anthropic"] = [OPUS, SONNET]
    (await client.post("/api/settings/models/refresh")).raise_for_status()
    return client


def choice(body: dict[str, Any]) -> ModelChoice:
    return ModelChoice(provider=body["provider"], model=body["model"], effort=body["effort"])


async def test_a_clipping_pasted_with_a_model_choice_is_read_with_it(
    with_sonnet: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    submitted = await with_sonnet.post(
        "/api/clippings", json={"pasted_text": PASTED_TEXT, "model_choice": SONNET_HIGH}
    )
    await run_queued_tasks()

    assert submitted.status_code == 201
    assert fake_llm.connections == [(choice(SONNET_HIGH), TEST_KEY)]
    clipping = (await with_sonnet.get(f"/api/clippings/{submitted.json()['id']}")).json()
    assert clipping["model_choice"] == SONNET_HIGH
    assert (clipping["provider"], clipping["model"]) == ("anthropic", "claude-sonnet-5")


@dataclass(frozen=True)
class Runs:
    """One run of each kind the user starts, done or failed: a failed Clipping, and a
    posting evaluated with an Application whose Cover Letter has one draft."""

    clipping_id: int
    posting_id: int
    application_id: int


async def runs_of_every_kind(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> Runs:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks)
    await generate(client, application["id"])
    await run_queued_tasks()
    fake_llm.manual_entry_extraction.respond_with(Failure("rejected", "Unknown model"))
    clipping = await submit_and_extract(client, run_queued_tasks)
    assert clipping["status"] == "failed"
    return Runs(clipping["id"], application["job_posting_id"], application["id"])


def starts(runs: Runs, given: dict[str, Any] | None) -> list[tuple[str, dict[str, Any]]]:
    """Each request that starts a run, as path and body, with the model choice `given`."""
    letter = f"/api/applications/{runs.application_id}/cover-letter"
    with_choice = {} if given is None else {"model_choice": given}
    return [
        ("/api/clippings", {"pasted_text": PASTED_TEXT, **with_choice}),
        (f"/api/clippings/{runs.clipping_id}/retry", with_choice),
        (f"/api/job-postings/{runs.posting_id}/evaluations", with_choice),
        (f"{letter}/generations", {"evaluation_case": "current", **with_choice}),
        (
            f"{letter}/revisions",
            {"evaluation_case": "current", "instruction": "Shorter.", **with_choice},
        ),
    ]


async def what_the_user_sees(client: httpx.AsyncClient, runs: Runs) -> list[Any]:
    """The runs of every kind as the API shows them."""
    return [
        (await client.get(f"/api/clippings/{runs.clipping_id}")).json(),
        (await client.get(f"/api/job-postings/{runs.posting_id}/evaluations")).json(),
        (await client.get(f"/api/applications/{runs.application_id}/cover-letter")).json(),
    ]


async def test_a_model_choice_that_cannot_be_used_is_refused_and_nothing_starts(
    with_sonnet: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    queued_tasks: Callable[[], Awaitable[list[str]]],
) -> None:
    client = with_sonnet
    runs = await runs_of_every_kind(client, fake_llm, run_queued_tasks)
    before = await what_the_user_sees(client, runs)
    await client.put("/api/settings/hidden-models/anthropic/claude-sonnet-5")

    refused = [
        await client.post(path, json=body)
        for given in [SONNET_HIGH, {**SONNET_HIGH, "model": "gpt-5"}]
        for path, body in starts(runs, given)
    ]

    assert [response.status_code for response in refused] == [422] * 10
    assert {response.json()["detail"] for response in refused} == {
        "Anthropic does not offer claude-sonnet-5, or it is hidden",
        "Anthropic does not offer gpt-5, or it is hidden",
    }
    assert await queued_tasks() == []
    assert await what_the_user_sees(client, runs) == before


async def test_an_effort_the_chosen_model_does_not_take_is_refused(
    with_sonnet: httpx.AsyncClient,
) -> None:
    refused = await with_sonnet.post(
        "/api/clippings",
        json={"pasted_text": PASTED_TEXT, "model_choice": {**SONNET_HIGH, "effort": "max"}},
    )

    assert refused.status_code == 422
    assert refused.json()["detail"] == "claude-sonnet-5 does not take the effort max"


async def test_with_no_choice_given_a_default_that_cannot_be_used_is_a_conflict(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    queued_tasks: Callable[[], Awaitable[list[str]]],
) -> None:
    runs = await runs_of_every_kind(client, fake_llm, run_queued_tasks)
    before = await what_the_user_sees(client, runs)
    await client.put("/api/settings/hidden-models/anthropic/claude-opus-5-5")

    refused = [await client.post(path, json=body) for path, body in starts(runs, None)]

    assert [response.status_code for response in refused] == [409] * 5
    hidden = "Anthropic does not offer claude-opus-5-5, or it is hidden"
    default = (
        f"The default model for this step cannot be used: {hidden}."
        " Choose another in Settings, or for this run"
    )
    kept = f"The model this run was queued with cannot be used: {hidden}. Choose another for it"
    assert [response.json()["detail"] for response in refused] == [
        default,
        kept,  # the Clipping retry keeps the model it was read with
        default,
        default,
        default,
    ]
    assert await queued_tasks() == []
    assert await what_the_user_sees(client, runs) == before


async def test_each_run_the_user_starts_calls_the_model_chosen_for_it(
    with_sonnet: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    client = with_sonnet
    runs = await runs_of_every_kind(client, fake_llm, run_queued_tasks)
    fake_llm.manual_entry_extraction.respond_with(an_extraction())
    efforts = ["low", "medium", "high", "low", "medium"]
    fake_llm.connections.clear()

    for (path, body), effort in zip(starts(runs, SONNET_HIGH), efforts, strict=True):
        started = await client.post(
            path, json={**body, "model_choice": {**SONNET_HIGH, "effort": effort}}
        )
        assert started.status_code in (200, 201)
        await run_queued_tasks()

    assert fake_llm.connections == [
        (choice({**SONNET_HIGH, "effort": effort}), TEST_KEY) for effort in efforts
    ]


async def test_a_clipping_retried_with_no_choice_keeps_the_one_it_was_read_with(
    with_sonnet: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    client = with_sonnet
    fake_llm.manual_entry_extraction.respond_with(Failure("rejected", "Unknown model"))
    failed = await submit_and_extract(client, run_queued_tasks, model_choice=SONNET_HIGH)
    # The step's default changes since: the retry still repeats what failed
    opus_low = {"provider": "anthropic", "model": "claude-opus-5-5", "effort": "low"}
    await client.put("/api/settings/defaults", json={"extraction": opus_low})
    fake_llm.manual_entry_extraction.respond_with(an_extraction())
    fake_llm.connections.clear()

    retried = await client.post(f"/api/clippings/{failed['id']}/retry")
    await run_queued_tasks()

    assert retried.status_code == 200
    assert retried.json()["model_choice"] == SONNET_HIGH
    assert fake_llm.connections == [(choice(SONNET_HIGH), TEST_KEY)]


async def test_a_clipping_retried_with_a_new_choice_is_read_with_that_one(
    with_sonnet: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    client = with_sonnet
    fake_llm.manual_entry_extraction.respond_with(Failure("rejected", "Unknown model"))
    failed = await submit_and_extract(client, run_queued_tasks)
    fake_llm.manual_entry_extraction.respond_with(an_extraction())
    fake_llm.connections.clear()

    retried = await client.post(
        f"/api/clippings/{failed['id']}/retry", json={"model_choice": SONNET_HIGH}
    )
    await run_queued_tasks()

    assert failed["model_choice"] == {"provider": "anthropic", "model": OPUS.id, "effort": None}
    assert retried.json()["model_choice"] == SONNET_HIGH
    assert fake_llm.connections == [(choice(SONNET_HIGH), TEST_KEY)]
    done = (await client.get(f"/api/clippings/{failed['id']}")).json()
    assert (done["status"], done["model"]) == ("done", "claude-sonnet-5")


def label(entry: dict[str, Any]) -> tuple[Any, ...]:
    """What an Evaluation was made with: the choice it was queued with, and the Provider and
    model that answered."""
    return (entry["status"], entry["model_choice"], entry["provider"], entry["model"])


async def test_the_evaluation_history_shows_each_ones_model_and_the_latest_done_is_current(
    with_sonnet: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    client = with_sonnet
    runs = await runs_of_every_kind(client, fake_llm, run_queued_tasks)
    evaluations = f"/api/job-postings/{runs.posting_id}/evaluations"
    await client.post(evaluations, json={"model_choice": SONNET_HIGH})
    await run_queued_tasks()
    fake_llm.evaluation.respond_with(Failure("rejected", "Unknown effort"))
    await client.post(evaluations, json={"model_choice": {**SONNET_HIGH, "effort": "low"}})
    await run_queued_tasks()

    history = (await client.get(evaluations)).json()
    current = (await client.get(f"{evaluations}/current")).json()

    opus = {"provider": "anthropic", "model": OPUS.id, "effort": None}
    assert [label(entry) for entry in history] == [
        ("failed", {**SONNET_HIGH, "effort": "low"}, "anthropic", "claude-sonnet-5"),
        ("done", SONNET_HIGH, "anthropic", "claude-sonnet-5"),
        ("done", opus, "anthropic", OPUS.id),  # the default, queued on confirming
    ]
    assert current["id"] == history[1]["id"]  # whatever model made it


def made_with(draft: dict[str, Any]) -> tuple[str | None, ...]:
    return (draft["text"], draft["provider"], draft["model"], draft["effort"])


async def test_each_cover_letter_draft_shows_the_provider_model_and_effort_it_was_made_with(
    with_sonnet: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    client = with_sonnet
    runs = await runs_of_every_kind(client, fake_llm, run_queued_tasks)
    letter = f"/api/applications/{runs.application_id}/cover-letter"
    fake_llm.cover_letter.respond_with(a_letter(letter="Revised by Sonnet."))
    revised = await client.post(
        f"{letter}/revisions",
        json={"evaluation_case": "current", "instruction": "Shorter.", "model_choice": SONNET_HIGH},
    )
    await run_queued_tasks()
    first = (await client.get(letter)).json()["drafts"][-1]
    await client.post(f"{letter}/drafts", json={"text": "By hand."})
    await client.post(f"{letter}/drafts/{first['id']}/restore")

    drafts = (await client.get(letter)).json()["drafts"]

    assert revised.json()["generation"]["model_choice"] == SONNET_HIGH
    assert [made_with(draft) for draft in drafts] == [
        (first["text"], "anthropic", OPUS.id, None),  # restored, with its record
        ("By hand.", None, None, None),
        ("Revised by Sonnet.", "anthropic", "claude-sonnet-5", "high"),
        (first["text"], "anthropic", OPUS.id, None),
    ]
