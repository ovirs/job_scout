"""The browser smoke test: paste, confirm and save, through the React app.

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


async def test_paste_confirm_and_save_a_manual_entry(
    page: Page,
    api_url: str,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    fake_llm.manual_entry_extraction.respond_with(an_extraction())

    await page.goto("/")
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


async def test_the_setup_screen_blocks_the_app_until_a_key_is_saved_and_returns_when_removed(
    page: Page, api_url: str
) -> None:
    async with httpx.AsyncClient(base_url=api_url) as client:
        await client.delete("/api/settings/providers/anthropic")

    await page.goto("/")
    await expect(page.get_by_role("heading", name="Welcome to Job Scout")).to_be_visible()
    await expect(page.get_by_role("navigation")).to_have_count(0)

    await page.get_by_label("API key").fill("sk-ant-typed-in-the-browser-9876")
    await page.get_by_role("button", name="Save key").click()
    await expect(page.get_by_role("navigation", name="Main")).to_be_visible()

    await page.get_by_role("link", name="Settings").click()
    anthropic = page.get_by_role("group", name="Anthropic")
    await expect(anthropic.get_by_text("9876")).to_be_visible()
    await expect(page.get_by_text("sk-ant-typed-in-the-browser-9876")).to_have_count(0)

    page.once("dialog", lambda dialog: dialog.accept())
    await anthropic.get_by_role("button", name="Remove key").click()
    await expect(page.get_by_role("heading", name="Welcome to Job Scout")).to_be_visible()
