"""The browser smoke test: set up a Provider on an empty database, then paste, confirm and
save, through the React app.

It checks the wiring from the frontend to the database; the API tests cover the
behaviour. The browser fixtures are in conftest.py.
"""

import re
from collections.abc import Awaitable, Callable

import httpx
import pytest
from clipping_helpers import PASTED_TEXT, an_extraction
from playwright.async_api import Page, expect

from job_scout.llm.fake import FakeLlm

pytestmark = pytest.mark.browser


async def test_set_up_then_paste_confirm_and_save_a_manual_entry(
    page: Page,
    api_url: str,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    fake_llm.manual_entry_extraction.respond_with(an_extraction())

    await page.goto("/#/deal-breakers")
    await expect(page.get_by_role("heading", name="Set up Job Scout")).to_be_visible()
    await expect(page.get_by_role("button", name="Add posting", exact=True)).to_be_hidden()
    await page.get_by_label("Anthropic API key").fill("sk-ant-browser-0000000000")
    await page.get_by_role("button", name="Save key").click()
    await expect(page.get_by_role("heading", name="Deal Breakers")).to_be_visible()

    await page.get_by_role("button", name="Add posting", exact=True).click()
    overlay = page.get_by_role("dialog", name="Add a job posting")
    await overlay.get_by_label("Paste the whole page").fill(PASTED_TEXT)
    await overlay.get_by_role("button", name="Read it").click()
    await expect(overlay).to_be_hidden()
    await expect(page.get_by_role("status")).to_have_text("Reading the pasted text…")

    await run_queued_tasks()

    await expect(page.get_by_role("heading", name="Check what was found")).to_be_visible()
    await expect(page.get_by_label("Company")).to_have_value("Acme")
    await page.get_by_label("Title").fill("Staff Data Engineer")
    await page.get_by_role("button", name="Save").click()

    await expect(page).to_have_url(re.compile(r"#/job-postings/\d+$"))
    await expect(page.get_by_role("heading", name="Staff Data Engineer")).to_be_visible()
    async with httpx.AsyncClient(base_url=api_url) as client:
        stored = (await client.get("/api/job-postings")).json()
    assert [(p["title"], p["company"]) for p in stored] == [("Staff Data Engineer", "Acme")]
