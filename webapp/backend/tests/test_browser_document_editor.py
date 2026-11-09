"""The Markdown editor on the Document pages, in the browser.

The editor has two modes: Write (the Markdown text and a formatting toolbar) and
Preview (the text rendered). The Document is stored as the plain Markdown text.
"""

import httpx
import pytest
from conftest import set_up_defaults, set_up_provider
from playwright.async_api import Locator, Page, expect

pytestmark = pytest.mark.browser


@pytest.fixture(autouse=True)
async def provider_set_up(api_url: str) -> None:
    """Past the setup screen, which shows until a Provider is set up."""
    async with httpx.AsyncClient(base_url=api_url) as client:
        await set_up_provider(client)
        await set_up_defaults(client)


async def save_document(api_url: str, kind: str, text: str) -> None:
    async with httpx.AsyncClient(base_url=api_url) as client:
        response = await client.post(f"/api/documents/{kind}/versions", json={"text": text})
        response.raise_for_status()


async def current_text(api_url: str, kind: str) -> str:
    async with httpx.AsyncClient(base_url=api_url) as client:
        text: str = (await client.get(f"/api/documents/{kind}")).json()["text"]
        return text


async def select(editor: Locator, text: str) -> None:
    """Select the first occurrence of text in the editor."""
    await editor.evaluate(
        "(el, text) => { const at = el.value.indexOf(text); el.focus();"
        " el.setSelectionRange(at, at + text.length) }",
        text,
    )


async def open_in_write(page: Page, kind: str, label: str, text: str, api_url: str) -> Locator:
    await save_document(api_url, kind, text)
    await page.goto(f"/#/{kind}")
    await page.get_by_role("button", name="Write").click()
    return page.get_by_label(label, exact=True)


async def test_format_save_and_see_the_new_version_rendered(page: Page, api_url: str) -> None:
    await save_document(api_url, "career-profile", "# Experience\n\nData engineer.")

    await page.goto("/#/career-profile")
    preview = page.get_by_role("region", name="Career Profile preview")
    await expect(preview.get_by_role("heading", name="Experience")).to_be_visible()
    await expect(page.get_by_label("Career Profile", exact=True)).to_be_hidden()

    await page.get_by_role("button", name="Write").click()
    editor = page.get_by_label("Career Profile", exact=True)
    await editor.press("ControlOrMeta+End")
    await editor.press_sequentially("\n\nSpark")
    await editor.press("Shift+Home")
    await page.get_by_role("toolbar", name="Formatting").get_by_role("button", name="Bold").click()
    await page.get_by_role("button", name="Save as a new version").click()

    await expect(page.get_by_text("Version 2")).to_be_visible()
    await expect(preview.locator("strong")).to_have_text("Spark")
    assert await current_text(api_url, "career-profile") == (
        "# Experience\n\nData engineer.\n\n**Spark**"
    )


async def test_an_unwritten_document_opens_in_write_and_edits_survive_a_switch(
    page: Page,
) -> None:
    await page.goto("/#/writing-guide")
    editor = page.get_by_label("Writing Guide", exact=True)
    await expect(editor).to_be_visible()

    await editor.fill("Short and *plain*.")
    await page.get_by_role("button", name="Preview").click()
    preview = page.get_by_role("region", name="Writing Guide preview")
    await expect(preview.locator("em")).to_have_text("plain")
    await page.get_by_role("button", name="Write").click()

    await expect(editor).to_have_value("Short and *plain*.")
    await expect(page.get_by_role("button", name="Save as a new version")).to_be_enabled()


async def test_shortcuts_toggle_bold_and_italic_and_undo_takes_them_back(
    page: Page, api_url: str
) -> None:
    editor = await open_in_write(page, "preferences", "Preferences", "Remote, Spark.", api_url)

    await select(editor, "Spark")
    await editor.press("ControlOrMeta+b")
    await expect(editor).to_have_value("Remote, **Spark**.")
    await editor.press("ControlOrMeta+i")
    await expect(editor).to_have_value("Remote, ***Spark***.")
    await editor.press("ControlOrMeta+b")
    await expect(editor).to_have_value("Remote, *Spark*.")
    await editor.press("ControlOrMeta+i")
    await expect(editor).to_have_value("Remote, Spark.")

    await editor.press("ControlOrMeta+z")
    await expect(editor).to_have_value("Remote, *Spark*.")
    await editor.press("ControlOrMeta+z")
    await expect(editor).to_have_value("Remote, ***Spark***.")


async def test_a_selection_that_includes_the_markers_toggles_off(page: Page, api_url: str) -> None:
    editor = await open_in_write(page, "preferences", "Preferences", "Remote, **Spark**.", api_url)

    await select(editor, "**Spark**")
    await page.get_by_role("button", name="Bold").click()

    await expect(editor).to_have_value("Remote, Spark.")


async def test_link_shortcut_wraps_the_selection_and_selects_the_address(
    page: Page, api_url: str
) -> None:
    editor = await open_in_write(page, "preferences", "Preferences", "See my site.", api_url)

    await select(editor, "my site")
    await editor.press("ControlOrMeta+k")
    await editor.press_sequentially("example.com")

    await expect(editor).to_have_value("See [my site](example.com).")


async def test_list_and_heading_buttons_apply_to_every_selected_line(
    page: Page, api_url: str
) -> None:
    editor = await open_in_write(
        page, "career-profile", "Career Profile", "Skills\nSpark\n\nKafka\n  Streams", api_url
    )
    tools = page.get_by_role("toolbar", name="Formatting")

    await select(editor, "Spark\n\nKafka\n  Streams")
    await tools.get_by_role("button", name="Numbered list").click()
    await expect(editor).to_have_value("Skills\n1. Spark\n\n2. Kafka\n  1. Streams")
    await tools.get_by_role("button", name="Bulleted list").click()
    await expect(editor).to_have_value("Skills\n- Spark\n\n- Kafka\n  - Streams")
    await tools.get_by_role("button", name="Bulleted list").click()
    await expect(editor).to_have_value("Skills\nSpark\n\nKafka\n  Streams")

    await select(editor, "Skills")
    await tools.get_by_role("button", name="Heading", exact=True).click()
    await expect(editor).to_have_value("## Skills\nSpark\n\nKafka\n  Streams")
    await tools.get_by_role("button", name="Subheading").click()
    await expect(editor).to_have_value("### Skills\nSpark\n\nKafka\n  Streams")
    await tools.get_by_role("button", name="Subheading").click()
    await expect(editor).to_have_value("Skills\nSpark\n\nKafka\n  Streams")
    await tools.get_by_role("button", name="Title").click()
    await expect(editor).to_have_value("# Skills\nSpark\n\nKafka\n  Streams")
    await tools.get_by_role("button", name="Heading", exact=True).click()
    await expect(editor).to_have_value("## Skills\nSpark\n\nKafka\n  Streams")


async def test_the_text_comes_back_byte_for_byte(page: Page, api_url: str) -> None:
    # Written as plain text before the editor: odd spacing, stray markers, no final newline
    plain = "\nLed the team -- 2019  \n\tSpark *and Kafka\n\n\n\n1) shipped\n<b>raw</b>   "
    editor = await open_in_write(page, "career-profile", "Career Profile", plain, api_url)
    save = page.get_by_role("button", name="Save as a new version")

    await expect(editor).to_have_value(plain)
    await select(editor, "Spark")
    await editor.press("ControlOrMeta+b")
    await expect(save).to_be_enabled()
    await editor.press("ControlOrMeta+z")
    await expect(editor).to_have_value(plain)
    await expect(save).to_be_disabled()

    await editor.press("ControlOrMeta+End")
    await editor.press_sequentially("x")
    await save.click()
    await expect(page.get_by_text("Version 2")).to_be_visible()
    assert await current_text(api_url, "career-profile") == plain + "x"


async def test_preview_renders_github_flavoured_markdown(page: Page, api_url: str) -> None:
    markdown = (
        "## Projects\n\n"
        "- **Pipeline** in *Spark*\n"
        "  - see [the repo](https://example.com/repo)\n"
        "- ~~Hadoop~~ and `kafka-streams`\n\n"
        "| Year | Role |\n| --- | --- |\n| 2019 | Lead |\n\n"
        "> Plain words."
    )
    await save_document(api_url, "career-profile", markdown)

    await page.goto("/#/career-profile")
    preview = page.get_by_role("region", name="Career Profile preview")
    await expect(preview.get_by_role("heading", name="Projects", level=2)).to_be_visible()
    await expect(preview.locator("strong")).to_have_text("Pipeline")
    await expect(preview.locator("em")).to_have_text("Spark")
    nested = preview.locator("ul ul").get_by_role("link", name="the repo")
    await expect(nested).to_have_attribute("href", "https://example.com/repo")
    await expect(preview.locator("del")).to_have_text("Hadoop")
    await expect(preview.locator("code")).to_have_text("kafka-streams")
    await expect(preview.get_by_role("cell", name="Lead")).to_be_visible()
    await expect(preview.locator("blockquote")).to_have_text("Plain words.")


async def test_a_heading_on_a_blank_first_line_goes_on_that_line(page: Page, api_url: str) -> None:
    editor = await open_in_write(page, "career-profile", "Career Profile", "\nSpark", api_url)

    await editor.evaluate("el => { el.focus(); el.setSelectionRange(0, 0) }")
    await page.get_by_role("button", name="Heading", exact=True).click()
    await editor.press_sequentially("Skills")

    await expect(editor).to_have_value("## Skills\nSpark")
