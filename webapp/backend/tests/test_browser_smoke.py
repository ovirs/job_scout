"""The one browser smoke test: paste, confirm and save, through the React app.

It drives the frontend's dev server in a headless browser, against the API
served from this process on the test database, with the fake LLM. It checks the
wiring from the frontend to the database; the API tests cover the behaviour.
Needs the frontend's packages (`npm ci` in webapp/frontend) and Chromium
(`uv run playwright install chromium`).
"""

import asyncio
import os
import re
import socket
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import httpx
import pytest
import uvicorn
from clipping_helpers import PASTED_TEXT, an_extraction
from playwright.async_api import Page, async_playwright, expect

from job_scout.api import create_app
from job_scout.config import Settings
from job_scout.llm.fake import FakeLlm

FRONTEND = Path(__file__).parents[2] / "frontend"

pytestmark = pytest.mark.browser


@pytest.fixture
async def api_url(settings: Settings) -> AsyncIterator[str]:
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning")
    )
    serving = asyncio.create_task(server.serve())
    while not server.started:
        if serving.done():
            serving.result()  # raises why it stopped
        await asyncio.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    await serving


@pytest.fixture
async def frontend_url(api_url: str) -> AsyncIterator[str]:
    vite = FRONTEND / "node_modules" / ".bin" / "vite"
    assert vite.exists(), "Install the frontend's packages: npm ci in webapp/frontend"
    port = _free_port()
    dev_server = await asyncio.create_subprocess_exec(
        str(vite),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--strictPort",
        cwd=FRONTEND,
        env={**os.environ, "API_URL": api_url},
        stdout=asyncio.subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        async with httpx.AsyncClient() as client:
            for _ in range(200):
                try:
                    await client.get(url)
                    break
                except httpx.TransportError:
                    await asyncio.sleep(0.1)
            else:
                pytest.fail("The frontend's dev server did not start")
        yield url
    finally:
        dev_server.terminate()
        await dev_server.wait()


@pytest.fixture
async def page(frontend_url: str) -> AsyncIterator[Page]:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(base_url=frontend_url)
        yield page
        await browser.close()


async def test_paste_confirm_and_save_a_manual_entry(
    page: Page,
    api_url: str,
    fake_llm: FakeLlm,
    run_queued_tasks: Callable[[], Awaitable[None]],
) -> None:
    fake_llm.manual_entry_extraction.respond_with(an_extraction())

    await page.goto("/")
    await page.get_by_label("Paste the whole page").fill(PASTED_TEXT)
    await page.get_by_role("button", name="Read it").click()
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


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port
