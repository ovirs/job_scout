"""Helpers for tests that start from a Clipping: a pasted text and its extraction."""

from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from job_scout.extraction import ManualEntryExtraction

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


ENVELOPE = {
    "title": "Senior Data Engineer",
    "company": "Acme",
    "location_text": "Bucharest, Romania",
    "workplace_type": "hybrid",
    "description": "Build and run our batch and streaming pipelines.",
}


async def save_manual_entry(
    client: httpx.AsyncClient,
    run_queued_tasks: Callable[[], Awaitable[None]],
    **envelope: object,
) -> dict[str, Any]:
    """Paste, extract and confirm a Manual Entry with this envelope; returns the posting."""
    clipping = await submit_and_extract(client, run_queued_tasks)
    confirmed = await client.post(
        f"/api/clippings/{clipping['id']}/confirm", json={**ENVELOPE, **envelope}
    )
    assert confirmed.status_code == 201
    posting: dict[str, Any] = confirmed.json()
    return posting
