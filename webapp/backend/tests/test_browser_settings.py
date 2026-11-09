"""The Settings page in the browser: Provider keys shown masked, removing the last one
returning the app to the setup screen, and hiding a model."""

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


async def test_a_model_hidden_in_settings_is_no_longer_offered(page: Page, api_url: str) -> None:
    async with httpx.AsyncClient(base_url=api_url) as client:
        await set_up_provider(client)

        await page.goto("/#/settings")
        opus = page.get_by_role("list", name="Anthropic models").get_by_role(
            "listitem", name="Claude Opus 5.5"
        )
        await expect(opus).to_contain_text("claude-opus-5-5")
        await opus.get_by_role("button", name="Hide").click()

        await expect(opus).to_contain_text("Hidden")
        await expect(opus.get_by_role("button", name="Offer again")).to_be_visible()
        assert (await client.get("/api/models")).json() == []
