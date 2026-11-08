"""The Settings page in the browser: Provider keys shown masked, and removing the last one
returning the app to the setup screen."""

import httpx
import pytest
from conftest import TEST_KEY, set_up_provider
from playwright.async_api import Dialog, Page, expect

pytestmark = pytest.mark.browser


async def test_removing_the_last_key_returns_the_app_to_the_setup_screen(
    page: Page, api_url: str
) -> None:
    async with httpx.AsyncClient(base_url=api_url) as client:
        await set_up_provider(client)

    async def accept(dialog: Dialog) -> None:
        await dialog.accept()

    page.on("dialog", accept)
    await page.goto("/#/settings")
    anthropic = page.get_by_role("listitem", name="Anthropic")
    await expect(anthropic).to_contain_text("sk-…0000")
    await expect(anthropic).not_to_contain_text(TEST_KEY)
    await anthropic.get_by_role("button", name="Remove key").click()

    await expect(page.get_by_role("heading", name="Set up Job Scout")).to_be_visible()
    await expect(page.get_by_role("navigation", name="Main")).to_be_hidden()
