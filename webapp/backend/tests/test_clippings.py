from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
import pytest
from clipping_helpers import ENVELOPE, PASTED_TEXT, an_extraction, submit_and_extract
from conftest import DEFAULT_CHOICE, TEST_KEY

from job_scout.clippings import domain as clippings
from job_scout.clippings.models import Clipping
from job_scout.config import Settings
from job_scout.llm import Failure
from job_scout.llm.fake import FakeLlm, FakeModelLister
from job_scout.llm.interface import STEPS
from job_scout.owners import LOCAL_USER_ID
from job_scout.prompts import MANUAL_ENTRY_EXTRACTION
from job_scout.runtime import Runtime, open_runtime
from job_scout.settings import domain as provider_settings

# The Clipping rules, at the package's interface


@pytest.fixture
async def runtime(settings: Settings) -> AsyncIterator[Runtime]:
    """The resources the package works with, the local user set up with Anthropic and a
    default for every step."""
    async with open_runtime(settings) as runtime:
        async with runtime.sessions() as session:
            await provider_settings.save_key(
                session,
                FakeModelLister(),
                owner_id=LOCAL_USER_ID,
                provider="anthropic",
                api_key=TEST_KEY,
            )
            await provider_settings.save_defaults(
                session,
                FakeModelLister(),
                owner_id=LOCAL_USER_ID,
                choices=dict.fromkeys(STEPS, DEFAULT_CHOICE),
            )
        yield runtime


async def a_clipping(
    runtime: Runtime, run_queued_tasks: Callable[[], Awaitable[None]], status: str
) -> int:
    """A Clipping of the local user in `status`: queued, done or failed; its id."""
    async with runtime.sessions() as session:
        clipping = await clippings.submit(
            session,
            runtime.task_queue,
            FakeModelLister(),
            owner_id=LOCAL_USER_ID,
            pasted_text=PASTED_TEXT,
            url=None,
        )
    if status != "queued":
        await run_queued_tasks()
    assert (await read(runtime, clipping.id)).status == status
    return clipping.id


async def read(runtime: Runtime, clipping_id: int) -> Clipping:
    async with runtime.sessions() as session:
        return await clippings.clipping(session, owner_id=LOCAL_USER_ID, clipping_id=clipping_id)


@pytest.mark.parametrize("status", ["queued", "done"])
async def test_only_a_failed_or_stuck_clipping_can_be_retried(
    runtime: Runtime, run_queued_tasks: Callable[[], Awaitable[None]], status: str
) -> None:
    clipping_id = await a_clipping(runtime, run_queued_tasks, status)

    with pytest.raises(clippings.WrongStatus):
        async with runtime.sessions() as session:
            await clippings.retry(
                session,
                runtime.task_queue,
                FakeModelLister(),
                owner_id=LOCAL_USER_ID,
                clipping_id=clipping_id,
            )

    assert (await read(runtime, clipping_id)).status == status


async def test_a_clipping_stuck_being_read_can_be_retried(
    runtime: Runtime,
    run_queued_tasks: Callable[[], Awaitable[None]],
    make_stuck: Callable[[str, int], None],
) -> None:
    clipping_id = await a_clipping(runtime, run_queued_tasks, "queued")
    make_stuck("clippings", clipping_id)

    async with runtime.sessions() as session:
        await clippings.retry(
            session,
            runtime.task_queue,
            FakeModelLister(),
            owner_id=LOCAL_USER_ID,
            clipping_id=clipping_id,
        )
    await run_queued_tasks()

    assert (await read(runtime, clipping_id)).status == "done"


async def abandon(runtime: Runtime, clipping_id: int) -> Clipping:
    async with runtime.sessions() as session:
        return await clippings.abandon(session, owner_id=LOCAL_USER_ID, clipping_id=clipping_id)


@pytest.mark.parametrize("status", ["done", "failed"])
async def test_a_done_or_failed_clipping_can_be_abandoned_and_is_kept(
    runtime: Runtime,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
    status: str,
) -> None:
    if status == "failed":
        fake_llm.manual_entry_extraction.respond_with(Failure("refusal", "The model declined"))
    clipping_id = await a_clipping(runtime, run_queued_tasks, status)

    await abandon(runtime, clipping_id)

    clipping = await read(runtime, clipping_id)
    assert clipping.status == "abandoned"
    assert clipping.pasted_text == PASTED_TEXT
    with pytest.raises(clippings.WrongStatus):
        async with runtime.sessions() as session:
            await clippings.retry(
                session,
                runtime.task_queue,
                FakeModelLister(),
                owner_id=LOCAL_USER_ID,
                clipping_id=clipping_id,
            )


@pytest.mark.parametrize("status", ["queued", "confirmed"])
async def test_a_clipping_still_being_read_or_confirmed_cannot_be_abandoned(
    runtime: Runtime, run_queued_tasks: Callable[[], Awaitable[None]], status: str
) -> None:
    clipping_id = await a_clipping(
        runtime, run_queued_tasks, "queued" if status == "queued" else "done"
    )
    if status == "confirmed":
        await confirm(runtime, clipping_id)

    with pytest.raises(clippings.WrongStatus):
        await abandon(runtime, clipping_id)

    assert (await read(runtime, clipping_id)).status == status


async def confirm(runtime: Runtime, clipping_id: int) -> clippings.Confirmed:
    async with runtime.sessions() as session:
        return await clippings.confirm(
            session,
            runtime.task_queue,
            FakeModelLister(),
            owner_id=LOCAL_USER_ID,
            clipping_id=clipping_id,
            title="Senior Data Engineer",
            company="Acme",
            location_text=None,
            workplace_type="remote",
            description="Build pipelines.",
        )


async def test_confirming_a_clipping_saves_its_posting_and_queues_its_evaluation(
    runtime: Runtime,
    run_queued_tasks: Callable[[], Awaitable[None]],
    queued_tasks: Callable[[], Awaitable[list[str]]],
) -> None:
    clipping_id = await a_clipping(runtime, run_queued_tasks, "done")

    confirmed = await confirm(runtime, clipping_id)

    assert confirmed.posting.title == "Senior Data Engineer"
    assert confirmed.posting.source == "manual"
    assert confirmed.evaluation.job_posting_id == confirmed.posting.id
    assert confirmed.evaluation.status == "queued"
    assert await queued_tasks() == ["evaluate"]
    clipping = await read(runtime, clipping_id)
    assert clipping.status == "confirmed"
    assert clipping.job_posting_id == confirmed.posting.id


@pytest.mark.parametrize("status", ["queued", "failed", "confirmed", "abandoned"])
async def test_only_a_done_clipping_can_be_confirmed(
    runtime: Runtime,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
    queued_tasks: Callable[[], Awaitable[list[str]]],
    status: str,
) -> None:
    if status == "failed":
        fake_llm.manual_entry_extraction.respond_with(Failure("refusal", "The model declined"))
    clipping_id = await a_clipping(
        runtime, run_queued_tasks, status if status in ("queued", "failed") else "done"
    )
    if status == "confirmed":
        await confirm(runtime, clipping_id)
        await run_queued_tasks()
    if status == "abandoned":
        await abandon(runtime, clipping_id)

    with pytest.raises(clippings.WrongStatus):
        await confirm(runtime, clipping_id)

    assert (await read(runtime, clipping_id)).status == status
    if status != "queued":
        assert await queued_tasks() == []  # no Evaluation queued


# The HTTP API


async def test_a_submitted_clipping_is_queued_until_the_worker_extracts_it(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    fake_llm.manual_entry_extraction.respond_with(an_extraction())

    submitted = await client.post("/api/clippings", json={"pasted_text": PASTED_TEXT})
    assert submitted.status_code == 201
    clipping_id = submitted.json()["id"]
    assert submitted.json()["status"] == "queued"
    assert submitted.json()["extraction"] is None
    assert fake_llm.manual_entry_extraction.calls == []  # never inside the request

    await run_queued_tasks()

    clipping = (await client.get(f"/api/clippings/{clipping_id}")).json()
    assert clipping["status"] == "done"
    assert clipping["failure"] is None
    extraction = clipping["extraction"]
    assert extraction["title"] == "Senior Data Engineer"
    assert extraction["company"] == "Acme"
    assert extraction["location_text"] == "Bucharest, Romania"
    assert extraction["description"] == (
        "About the job\n"
        "We are building the data platform behind Acme's payments.\n"
        "You will design batch and streaming pipelines in Python, Go or Java.\n"
        "Salary: 90,000 to 110,000 EUR a year.\n"
        "Equal opportunity employer."
    )
    assert extraction["description_cut"] is True
    assert fake_llm.manual_entry_extraction.calls == [PASTED_TEXT]


@pytest.mark.parametrize(
    ("first_line", "last_line"),
    [
        ("About this role", "Equal opportunity employer."),  # first line not in the pasted text
        ("About the job", "We are an equal opportunity employer."),  # last line not in it
        (None, "Equal opportunity employer."),
        ("About the job", None),
        ("Equal opportunity employer.", "About the job"),  # last line only before the first
    ],
)
async def test_without_both_markers_the_whole_pasted_text_is_the_description(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
    first_line: str | None,
    last_line: str | None,
) -> None:
    fake_llm.manual_entry_extraction.respond_with(
        an_extraction(description_first_line=first_line, description_last_line=last_line)
    )

    clipping = await submit_and_extract(client, run_queued_tasks)

    assert clipping["status"] == "done"
    assert clipping["extraction"]["description"] == PASTED_TEXT
    assert clipping["extraction"]["description_cut"] is False


async def test_the_cut_takes_whole_lines_from_the_first_marker_to_the_next_last_marker(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    pasted_text = (
        "Jobs you may like: Data Engineer at Globex\n"
        "  About the job  \n"
        "Build pipelines.\n"
        "Apply now\n"
        "About the job at Globex\n"
        "Apply now\n"
    )
    # Markers given as parts of their lines, with stray spaces
    fake_llm.manual_entry_extraction.respond_with(
        an_extraction(description_first_line=" About the", description_last_line="Apply ")
    )

    clipping = await submit_and_extract(client, run_queued_tasks, pasted_text=pasted_text)

    assert clipping["extraction"]["description"] == "  About the job  \nBuild pipelines.\nApply now"
    assert clipping["extraction"]["description_cut"] is True


async def test_a_failed_clipping_shows_why_and_waits_for_a_retry(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    fake_llm.manual_entry_extraction.respond_with(Failure("refusal", "The model declined"))

    clipping = await submit_and_extract(client, run_queued_tasks)

    assert clipping["status"] == "failed"
    assert clipping["failure"] == {"kind": "refusal", "reason": "The model declined"}
    assert clipping["extraction"] is None
    assert len(fake_llm.manual_entry_extraction.calls) == 3

    await run_queued_tasks()
    assert len(fake_llm.manual_entry_extraction.calls) == 3  # nothing left on the queue

    fake_llm.manual_entry_extraction.respond_with(an_extraction())
    retried = await client.post(f"/api/clippings/{clipping['id']}/retry")
    assert retried.status_code == 200
    assert retried.json()["status"] == "queued"
    assert retried.json()["failure"] is None

    await run_queued_tasks()

    clipping = (await client.get(f"/api/clippings/{clipping['id']}")).json()
    assert clipping["status"] == "done"
    assert clipping["extraction"]["title"] == "Senior Data Engineer"


async def test_extracted_facts_keep_every_salary_range_seniority_and_alternative(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    facts = {
        "salary_ranges": [
            {
                "minimum": 90000.0,
                "maximum": 110000.0,
                "currency": "EUR",
                "period": "year",
                "applies_to": "Romania",
            },
            {
                "minimum": None,
                "maximum": 160000.0,
                "currency": "USD",
                "period": "year",
                "applies_to": None,
            },
        ],
        "seniority": ["senior", "staff"],
        "employment_type": "full_time",
        "workplace_type": "hybrid",
        "location_restriction": "Two days a week in the Bucharest office",
        "required_technologies": [
            {"name": "Python", "alternative_group": 1},
            {"name": "Go", "alternative_group": 1},
            {"name": "Java", "alternative_group": 1},
            {"name": "PostgreSQL", "alternative_group": None},
        ],
        "nice_to_have_technologies": [{"name": "Apache Kafka", "alternative_group": None}],
    }
    fake_llm.manual_entry_extraction.respond_with(an_extraction(**facts))

    clipping = await submit_and_extract(client, run_queued_tasks)

    assert clipping["extraction"]["extracted_fields"] == facts


async def test_a_clipping_keeps_its_pasted_text_url_model_and_prompt_version(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    url = "https://www.linkedin.com/jobs/view/4012345678/"

    clipping = await submit_and_extract(client, run_queued_tasks, url=url)

    assert clipping["pasted_text"] == PASTED_TEXT
    assert clipping["url"] == url
    assert clipping["model"] == "claude-opus-5-5"  # the default for every step
    assert clipping["prompt_version"] == MANUAL_ENTRY_EXTRACTION.version


@pytest.mark.parametrize(
    "body",
    [{}, {"pasted_text": ""}, {"pasted_text": " \n\t "}, {"pasted_text": PASTED_TEXT, "url": " "}],
)
async def test_a_clipping_must_have_some_text(
    client: httpx.AsyncClient, body: dict[str, object]
) -> None:
    submitted = await client.post("/api/clippings", json=body)

    assert submitted.status_code == 422


async def test_an_unknown_clipping_is_not_found(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/clippings/1")).status_code == 404
    assert (await client.post("/api/clippings/1/retry")).status_code == 404


async def test_a_refused_operation_is_a_conflict(client: httpx.AsyncClient) -> None:
    clipping = (await client.post("/api/clippings", json={"pasted_text": PASTED_TEXT})).json()
    path = f"/api/clippings/{clipping['id']}"

    retried = await client.post(f"{path}/retry")
    confirmed = await client.post(f"{path}/confirm", json=ENVELOPE)
    abandoned = await client.post(f"{path}/abandon")

    assert retried.status_code == 409
    assert retried.json()["detail"] == (
        "Only a failed Clipping, or one stuck being read, can be retried"
    )
    assert confirmed.status_code == 409
    assert abandoned.status_code == 409


async def test_a_last_marker_also_found_in_the_first_line_ends_the_cut_further_down(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    pasted_text = "Menu\nJoin the payments team\nBuild pipelines.\nWe pay well.\nFooter\n"
    fake_llm.manual_entry_extraction.respond_with(
        an_extraction(description_first_line="Join the payments team", description_last_line="pay")
    )

    clipping = await submit_and_extract(client, run_queued_tasks, pasted_text=pasted_text)

    assert clipping["extraction"]["description"] == (
        "Join the payments team\nBuild pipelines.\nWe pay well."
    )


async def test_a_one_line_description_is_cut_from_its_line(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    pasted_text = "Menu\nBuild pipelines for payments.\nFooter\n"
    line = "Build pipelines for payments."
    fake_llm.manual_entry_extraction.respond_with(
        an_extraction(description_first_line=line, description_last_line=line)
    )

    clipping = await submit_and_extract(client, run_queued_tasks, pasted_text=pasted_text)

    assert clipping["extraction"]["description"] == line
