"""Test harness: the HTTP API against a real Postgres, with queued tasks run in-test.

One Postgres container per session. Migrations run once into a template
database; every test gets a fresh database cloned from it.

Browser tests drive the frontend's dev server in a headless browser, against the
API served from this process on the test database, with the fake LLM. They need
the frontend's packages (`npm ci` in webapp/frontend) and Chromium
(`uv run playwright install chromium`).
"""

import asyncio
import os
import socket
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from pathlib import Path

import httpx
import psycopg
import pytest
import uvicorn
from asgi_lifespan import LifespanManager
from playwright.async_api import Page, async_playwright
from testcontainers.community.postgres import PostgresContainer

from job_scout import migrations, queue, worker
from job_scout.app import create_app
from job_scout.config import Settings
from job_scout.llm.fake import FakeLlm, FakeModelLister
from job_scout.llm.interface import ModelChoice
from job_scout.llm_runs.domain import STUCK_AFTER

TEMPLATE_DATABASE = "job_scout_template"

# The Anthropic key the `client` fixture sets up, which the fake lister accepts
TEST_KEY = "sk-ant-test-0000000000000000"
FRONTEND = Path(__file__).parents[2] / "frontend"


@pytest.fixture(scope="session")
def postgres_server() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:17-alpine", driver=None) as server:
        with psycopg.connect(server.get_connection_url(), autocommit=True) as conn:
            conn.execute(f"CREATE DATABASE {TEMPLATE_DATABASE}")
        migrations.upgrade(_database_url(server, TEMPLATE_DATABASE))
        yield server


@pytest.fixture
def settings(postgres_server: PostgresContainer) -> Iterator[Settings]:
    name = f"test_{uuid.uuid4().hex}"
    admin_url = postgres_server.get_connection_url()
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f"CREATE DATABASE {name} TEMPLATE {TEMPLATE_DATABASE}")
    yield Settings(database_url=_database_url(postgres_server, name), llm_retry_wait_seconds=0)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE {name} WITH (FORCE)")


@pytest.fixture
def fake_lister() -> FakeModelLister:
    """What the API checks a key with in tests: lists canned models, or refuses."""
    return FakeModelLister()


@pytest.fixture
async def client_without_provider(
    settings: Settings, fake_lister: FakeModelLister
) -> AsyncIterator[httpx.AsyncClient]:
    """The API on an empty database, with no Provider set up yet."""
    app = create_app(settings, model_lister=fake_lister)
    async with LifespanManager(app) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture
async def client_with_provider_only(
    client_without_provider: httpx.AsyncClient,
) -> httpx.AsyncClient:
    """The API with Anthropic's key saved, `TEST_KEY`, and no default model chosen yet."""
    await set_up_provider(client_without_provider)
    return client_without_provider


@pytest.fixture
async def client(client_with_provider_only: httpx.AsyncClient) -> httpx.AsyncClient:
    """The API set up: Anthropic with `TEST_KEY`, and `DEFAULT_CHOICE` for every step."""
    await set_up_defaults(client_with_provider_only)
    return client_with_provider_only


# The default model choice the `client` fixture sets up for every step
DEFAULT_CHOICE = ModelChoice(provider="anthropic", model="claude-opus-5-5", effort=None)


async def set_up_provider(client: httpx.AsyncClient) -> None:
    response = await client.put("/api/settings/providers/anthropic/key", json={"api_key": TEST_KEY})
    response.raise_for_status()


async def set_up_defaults(client: httpx.AsyncClient) -> None:
    choice = {"provider": "anthropic", "model": DEFAULT_CHOICE.model, "effort": None}
    response = await client.put(
        "/api/settings/defaults",
        json={"extraction": choice, "evaluation": choice, "cover_letter": choice},
    )
    response.raise_for_status()


@pytest.fixture
def fake_llm() -> FakeLlm:
    """The LLM the worker calls in tests: give it canned outcomes, read its calls."""
    return FakeLlm()


@pytest.fixture
def run_queued_tasks(settings: Settings, fake_llm: FakeLlm) -> Callable[[], Awaitable[None]]:
    """Run every queued task to completion, retries included, then return."""

    async def run() -> None:
        await worker.run(settings, connect=fake_llm.connect, wait=False)

    return run


@pytest.fixture
def queued_tasks(settings: Settings) -> Callable[[], Awaitable[list[str]]]:
    """The names of the tasks waiting in the queue."""

    async def list_queued() -> list[str]:
        task_queue = queue.build(settings)
        async with task_queue.open_async():
            jobs = await task_queue.job_manager.list_jobs_async(status="todo")
        return [job.task_name for job in jobs]

    return list_queued


@pytest.fixture
def make_stuck(settings: Settings) -> Callable[[str, int], None]:
    """Make an LLM run, by its table and id, look queued or running for longer than
    any run takes, as if its worker died."""

    def make(table: str, run_id: int) -> None:
        with psycopg.connect(settings.database_url) as conn:
            conn.execute(
                f"UPDATE {table} SET queued_at = queued_at - %(by)s,"
                " started_at = started_at - %(by)s WHERE id = %(id)s",
                {"by": STUCK_AFTER * 2, "id": run_id},
            )

    return make


@pytest.fixture
async def api_url(settings: Settings) -> AsyncIterator[str]:
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings, model_lister=FakeModelLister()),
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
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


def _database_url(server: PostgresContainer, database: str) -> str:
    host = server.get_container_host_ip()
    port = server.get_exposed_port(server.port)
    return f"postgresql://{server.username}:{server.password}@{host}:{port}/{database}"


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port
