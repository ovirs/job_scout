"""Test harness: the HTTP API against a real Postgres, with queued tasks run in-test.

One Postgres container per session. Migrations run once into a template
database; every test gets a fresh database cloned from it.
"""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator

import httpx
import psycopg
import pytest
from asgi_lifespan import LifespanManager
from testcontainers.community.postgres import PostgresContainer

from job_scout import migrations, queue, worker
from job_scout.api import create_app
from job_scout.config import Settings

TEMPLATE_DATABASE = "job_scout_template"


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
    yield Settings(database_url=_database_url(postgres_server, name))
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE {name} WITH (FORCE)")


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings)
    async with LifespanManager(app) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture
def run_queued_tasks(settings: Settings) -> Callable[[], Awaitable[None]]:
    """Run every queued task to completion, then return."""

    async def run() -> None:
        await worker.run(settings, wait=False)

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


def _database_url(server: PostgresContainer, database: str) -> str:
    host = server.get_container_host_ip()
    port = server.get_exposed_port(server.port)
    return f"postgresql://{server.username}:{server.password}@{host}:{port}/{database}"
