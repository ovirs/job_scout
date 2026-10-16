from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest

from job_scout.extraction import ManualEntryExtraction
from job_scout.llm import Failure
from job_scout.llm.fake import FakeLlm
from job_scout.prompts import MANUAL_ENTRY_EXTRACTION

PASTED_TEXT = """Home  Jobs  Messaging  Notifications
Senior Data Engineer
Acme · Bucharest, Romania (Hybrid)
About the job
We are building the data platform behind Acme's payments.
You will design batch and streaming pipelines in Python, Go or Java.
Salary: 90,000 to 110,000 EUR a year.
Equal opportunity employer.
Show more jobs like this
Similar jobs: Data Engineer at Globex
"""


def an_extraction(**changes: object) -> ManualEntryExtraction:
    fields: dict[str, object] = {
        "title": "Senior Data Engineer",
        "company": "Acme",
        "location_text": "Bucharest, Romania",
        "description_first_line": "About the job",
        "description_last_line": "Equal opportunity employer.",
        "salary_ranges": [],
        "seniority": ["senior"],
        "employment_type": None,
        "workplace_type": "hybrid",
        "location_restriction": None,
        "required_technologies": [],
        "nice_to_have_technologies": [],
    }
    return ManualEntryExtraction.model_validate({**fields, **changes})


async def test_a_submitted_clipping_is_pending_until_the_worker_extracts_it(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    fake_llm.manual_entry_extraction.respond_with(an_extraction())

    submitted = await client.post("/api/clippings", json={"pasted_text": PASTED_TEXT})
    assert submitted.status_code == 201
    clipping_id = submitted.json()["id"]
    assert submitted.json()["status"] == "pending"
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


async def submit_and_extract(
    client: httpx.AsyncClient,
    run_queued_tasks: Callable[[], Awaitable[None]],
    **body: object,
) -> dict[str, Any]:
    submitted = await client.post("/api/clippings", json={"pasted_text": PASTED_TEXT, **body})
    assert submitted.status_code == 201
    await run_queued_tasks()
    clipping: dict[str, Any] = (await client.get(f"/api/clippings/{submitted.json()['id']}")).json()
    return clipping


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


async def test_a_failed_extraction_is_retried_on_the_queue(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    overloaded = Failure("error", "The Anthropic API is overloaded")
    fake_llm.manual_entry_extraction.respond_with(overloaded, overloaded, an_extraction())

    clipping = await submit_and_extract(client, run_queued_tasks)

    assert clipping["status"] == "done"
    assert clipping["failure"] is None
    assert len(fake_llm.manual_entry_extraction.calls) == 3


async def test_after_three_failed_attempts_the_clipping_shows_why_and_waits_for_a_retry(
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
    assert retried.json()["status"] == "pending"
    assert retried.json()["failure"] is None

    await run_queued_tasks()

    clipping = (await client.get(f"/api/clippings/{clipping['id']}")).json()
    assert clipping["status"] == "done"
    assert clipping["extraction"]["title"] == "Senior Data Engineer"


@pytest.mark.parametrize("status", ["pending", "done"])
async def test_only_a_failed_clipping_can_be_retried(
    client: httpx.AsyncClient,
    run_queued_tasks: Callable[[], Awaitable[None]],
    status: str,
) -> None:
    clipping = (await client.post("/api/clippings", json={"pasted_text": PASTED_TEXT})).json()
    if status == "done":
        await run_queued_tasks()

    retried = await client.post(f"/api/clippings/{clipping['id']}/retry")

    assert retried.status_code == 409
    assert (await client.get(f"/api/clippings/{clipping['id']}")).json()["status"] == status


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


async def test_an_unexpected_error_also_ends_in_failed_with_its_reason(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    fake_llm.manual_entry_extraction.respond_with(RuntimeError("connection reset"))

    clipping = await submit_and_extract(client, run_queued_tasks)

    assert clipping["status"] == "failed"
    assert clipping["failure"]["kind"] == "error"
    assert "connection reset" in clipping["failure"]["reason"]
    assert len(fake_llm.manual_entry_extraction.calls) == 3


async def test_an_unexpected_error_after_a_failed_call_names_no_model_or_prompt(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    fake_llm.manual_entry_extraction.respond_with(Failure("refusal", "The model declined"))
    clipping = await submit_and_extract(client, run_queued_tasks)
    assert clipping["model"] == "claude-opus-5-5"

    fake_llm.manual_entry_extraction.respond_with(RuntimeError("connection reset"))
    await client.post(f"/api/clippings/{clipping['id']}/retry")
    await run_queued_tasks()

    clipping = (await client.get(f"/api/clippings/{clipping['id']}")).json()
    assert clipping["failure"]["kind"] == "error"
    assert clipping["model"] is None
    assert clipping["prompt_version"] is None


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
