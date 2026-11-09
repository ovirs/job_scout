"""The Settings page in the browser: Provider keys shown masked, removing the last one
returning the app to the setup screen, hiding a model, and each step's default model."""

import httpx
import pytest
from conftest import TEST_KEY, set_up_defaults, set_up_provider
from playwright.async_api import Dialog, Page, expect

pytestmark = pytest.mark.browser


async def test_removing_the_last_key_returns_the_app_to_the_setup_screen(
    page: Page, api_url: str
) -> None:
    async with httpx.AsyncClient(base_url=api_url) as client:
        await set_up_provider(client)
        await set_up_defaults(client)

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
        await set_up_defaults(client)

        await page.goto("/#/settings")
        opus = page.get_by_role("list", name="Anthropic models").get_by_role(
            "listitem", name="Claude Opus 5.5"
        )
        await expect(opus).to_contain_text("claude-opus-5-5")
        await opus.get_by_role("button", name="Hide").click()

        await expect(opus).to_contain_text("Hidden")
        await expect(opus.get_by_role("button", name="Offer again")).to_be_visible()
        assert (await client.get("/api/models")).json() == []


async def test_a_steps_default_is_changed_and_a_default_that_cannot_be_used_is_flagged(
    page: Page, api_url: str
) -> None:
    async with httpx.AsyncClient(base_url=api_url) as client:
        await set_up_provider(client)
        await set_up_defaults(client)

        await page.goto("/#/settings")
        evaluation = page.get_by_role("listitem", name="Evaluating a Job Posting")
        await expect(evaluation).to_contain_text("Claude Opus 5.5")
        await evaluation.get_by_label("Effort").select_option("max")
        await evaluation.get_by_role("button", name="Save").click()
        await expect(evaluation).to_contain_text("effort max")

        opus = page.get_by_role("list", name="Anthropic models").get_by_role(
            "listitem", name="Claude Opus 5.5"
        )
        await opus.get_by_role("button", name="Hide").click()

        await expect(evaluation.get_by_role("alert")).to_have_text(
            "This default cannot be used: Anthropic does not offer claude-opus-5-5, or it is"
            " hidden. Runs of this step fail until you choose another."
        )
        defaults = (await client.get("/api/settings/defaults")).json()
        assert [default["choice"]["effort"] for default in defaults] == [None, "max", None]
