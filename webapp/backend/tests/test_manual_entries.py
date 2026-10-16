from collections.abc import Awaitable, Callable

import httpx
import pytest
from clipping_helpers import (
    ENVELOPE,
    PASTED_TEXT,
    an_extraction,
    save_manual_entry,
    submit_and_extract,
)

from job_scout.llm import Failure
from job_scout.llm.fake import NOTHING_FOUND, FakeLlm

URL = "https://www.linkedin.com/jobs/view/4012345678/"


async def test_the_corrections_made_on_confirmation_are_what_gets_stored(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    fake_llm.manual_entry_extraction.respond_with(
        an_extraction(seniority=["senior", "staff"], employment_type="full_time")
    )
    clipping = await submit_and_extract(client, run_queued_tasks, url=URL)

    confirmed = await client.post(
        f"/api/clippings/{clipping['id']}/confirm",
        json={
            "title": "Staff Data Engineer",
            "company": "Acme Payments",
            "location_text": "Cluj-Napoca, Romania",
            "workplace_type": "remote",
            "description": "We are building the data platform behind Acme's payments.",
        },
    )

    assert confirmed.status_code == 201
    posting = (await client.get(f"/api/job-postings/{confirmed.json()['id']}")).json()
    assert posting["source"] == "manual"
    assert posting["title"] == "Staff Data Engineer"
    assert posting["company"] == "Acme Payments"
    assert posting["location_text"] == "Cluj-Napoca, Romania"
    assert posting["workplace_type"] == "remote"
    assert posting["description"] == "We are building the data platform behind Acme's payments."
    assert posting["url"] == URL
    assert posting["pasted_text"] == PASTED_TEXT
    assert posting["closed_at"] is None
    # Stored as extracted, not extracted again, but with the corrected workplace type
    assert posting["extracted_fields"] == {
        **clipping["extraction"]["extracted_fields"],
        "workplace_type": "remote",
    }
    assert clipping["extraction"]["extracted_fields"]["workplace_type"] == "hybrid"
    assert posting["extracted_fields"]["seniority"] == ["senior", "staff"]
    assert len(fake_llm.manual_entry_extraction.calls) == 1


async def test_a_clipping_is_confirmed_once_and_points_at_its_manual_entry(
    client: httpx.AsyncClient, run_queued_tasks: Callable[[], Awaitable[None]]
) -> None:
    clipping = await submit_and_extract(client, run_queued_tasks)
    path = f"/api/clippings/{clipping['id']}/confirm"

    posting = (await client.post(path, json=ENVELOPE)).json()
    again = await client.post(path, json=ENVELOPE)

    assert again.status_code == 409
    clipping = (await client.get(f"/api/clippings/{clipping['id']}")).json()
    assert clipping["status"] == "confirmed"
    assert clipping["job_posting_id"] == posting["id"]
    assert clipping["extraction"] is not None  # still shown
    assert [p["id"] for p in (await client.get("/api/job-postings")).json()] == [posting["id"]]


async def test_a_clipping_not_yet_read_or_whose_reading_failed_cannot_be_confirmed(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    pending = (await client.post("/api/clippings", json={"pasted_text": PASTED_TEXT})).json()
    assert (
        await client.post(f"/api/clippings/{pending['id']}/confirm", json=ENVELOPE)
    ).status_code == 409

    fake_llm.manual_entry_extraction.respond_with(Failure("refusal", "The model declined"))
    await run_queued_tasks()
    assert (
        await client.post(f"/api/clippings/{pending['id']}/confirm", json=ENVELOPE)
    ).status_code == 409

    assert (await client.get("/api/job-postings")).json() == []


@pytest.mark.parametrize(
    "changes",
    [{"title": " "}, {"company": ""}, {"description": " \n "}, {"workplace_type": "office"}],
)
async def test_a_manual_entry_needs_a_title_company_description_and_known_workplace_type(
    client: httpx.AsyncClient,
    run_queued_tasks: Callable[[], Awaitable[None]],
    changes: dict[str, object],
) -> None:
    clipping = await submit_and_extract(client, run_queued_tasks)

    confirmed = await client.post(
        f"/api/clippings/{clipping['id']}/confirm", json={**ENVELOPE, **changes}
    )

    assert confirmed.status_code == 422
    assert (await client.get(f"/api/clippings/{clipping['id']}")).json()["status"] == "done"


async def test_location_and_workplace_type_may_be_left_empty(
    client: httpx.AsyncClient, run_queued_tasks: Callable[[], Awaitable[None]]
) -> None:
    posting = await save_manual_entry(
        client, run_queued_tasks, location_text=None, workplace_type=None
    )

    assert posting["location_text"] is None
    assert posting["workplace_type"] is None


async def test_facts_the_posting_does_not_state_are_stored_as_missing(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    fake_llm.manual_entry_extraction.respond_with(NOTHING_FOUND)

    posting = await save_manual_entry(client, run_queued_tasks, workplace_type=None)

    assert posting["extracted_fields"] == {
        "salary_ranges": [],
        "seniority": [],
        "employment_type": None,
        "workplace_type": None,
        "location_restriction": None,
        "required_technologies": [],
        "nice_to_have_technologies": [],
    }


async def test_an_unknown_clipping_cannot_be_confirmed_or_abandoned(
    client: httpx.AsyncClient,
) -> None:
    assert (await client.post("/api/clippings/1/confirm", json=ENVELOPE)).status_code == 404
    assert (await client.post("/api/clippings/1/abandon")).status_code == 404


async def test_similar_postings_are_from_the_same_company_with_the_closest_title_first(
    client: httpx.AsyncClient, run_queued_tasks: Callable[[], Awaitable[None]]
) -> None:
    stored = {}
    for company, title in [
        ("acme", "Office Manager"),
        ("Acme", "Senior Data Engineer"),
        ("ACME", "Engineer"),
        ("Ac me", "Senior  data engineer (Payments)"),
        ("Globex", "Senior Data Engineer"),
        ("Acme Payments", "Senior Data Engineer"),
    ]:
        posting = await save_manual_entry(client, run_queued_tasks, company=company, title=title)
        stored[(company, title)] = posting["id"]

    similar = await client.get(
        "/api/job-postings/similar", params={"company": "Acme", "title": "senior data engineer"}
    )

    assert similar.status_code == 200
    assert [(p["company"], p["title"]) for p in similar.json()] == [
        ("Acme", "Senior Data Engineer"),
        ("Ac me", "Senior  data engineer (Payments)"),
        ("ACME", "Engineer"),
        ("acme", "Office Manager"),
    ]
    assert similar.json()[0]["id"] == stored[("Acme", "Senior Data Engineer")]


async def test_a_company_with_no_stored_postings_has_no_similar_ones(
    client: httpx.AsyncClient, run_queued_tasks: Callable[[], Awaitable[None]]
) -> None:
    await save_manual_entry(client, run_queued_tasks, company="Acme")

    similar = await client.get(
        "/api/job-postings/similar", params={"company": "Globex", "title": "Data Engineer"}
    )

    assert similar.json() == []


async def test_an_abandoned_clipping_stores_no_posting_and_can_no_longer_be_confirmed(
    client: httpx.AsyncClient, run_queued_tasks: Callable[[], Awaitable[None]]
) -> None:
    existing = await save_manual_entry(client, run_queued_tasks)
    clipping = await submit_and_extract(client, run_queued_tasks)

    abandoned = await client.post(f"/api/clippings/{clipping['id']}/abandon")

    assert abandoned.status_code == 200
    assert abandoned.json()["status"] == "abandoned"
    assert abandoned.json()["pasted_text"] == PASTED_TEXT  # kept, not deleted
    confirmed = await client.post(f"/api/clippings/{clipping['id']}/confirm", json=ENVELOPE)
    assert confirmed.status_code == 409
    assert [p["id"] for p in (await client.get("/api/job-postings")).json()] == [existing["id"]]


async def test_a_clipping_whose_reading_failed_can_be_abandoned(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    fake_llm.manual_entry_extraction.respond_with(Failure("refusal", "The model declined"))
    clipping = await submit_and_extract(client, run_queued_tasks)

    abandoned = await client.post(f"/api/clippings/{clipping['id']}/abandon")

    assert abandoned.json()["status"] == "abandoned"
    assert (await client.post(f"/api/clippings/{clipping['id']}/retry")).status_code == 409


async def test_a_clipping_still_being_read_or_confirmed_cannot_be_abandoned(
    client: httpx.AsyncClient, run_queued_tasks: Callable[[], Awaitable[None]]
) -> None:
    pending = (await client.post("/api/clippings", json={"pasted_text": PASTED_TEXT})).json()
    assert (await client.post(f"/api/clippings/{pending['id']}/abandon")).status_code == 409

    await run_queued_tasks()
    await client.post(f"/api/clippings/{pending['id']}/confirm", json=ENVELOPE)
    assert (await client.post(f"/api/clippings/{pending['id']}/abandon")).status_code == 409
    assert (await client.get(f"/api/clippings/{pending['id']}")).json()["status"] == "confirmed"


async def test_closing_sets_a_closed_date_and_reopening_clears_it_without_deleting(
    client: httpx.AsyncClient, run_queued_tasks: Callable[[], Awaitable[None]]
) -> None:
    posting = await save_manual_entry(client, run_queued_tasks)
    path = f"/api/job-postings/{posting['id']}"

    closed = await client.post(f"{path}/close")

    assert closed.status_code == 200
    closed_at = closed.json()["closed_at"]
    assert closed_at is not None
    assert (await client.get(path)).json()["closed_at"] == closed_at
    assert [p["id"] for p in (await client.get("/api/job-postings")).json()] == [posting["id"]]
    # Closing again keeps the date it first closed on
    assert (await client.post(f"{path}/close")).json()["closed_at"] == closed_at
    # A closed posting is still a possible duplicate
    similar = await client.get(
        "/api/job-postings/similar", params={"company": "Acme", "title": "Data Engineer"}
    )
    assert [p["id"] for p in similar.json()] == [posting["id"]]

    reopened = await client.post(f"{path}/reopen")

    assert reopened.status_code == 200
    assert reopened.json()["closed_at"] is None
    assert (await client.get(path)).json() == {**closed.json(), "closed_at": None}


async def test_an_unknown_posting_cannot_be_closed_or_reopened(client: httpx.AsyncClient) -> None:
    assert (await client.post("/api/job-postings/1/close")).status_code == 404
    assert (await client.post("/api/job-postings/1/reopen")).status_code == 404
