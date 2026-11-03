"""The backend's layout holds (ADR-0004): every table is registered, the migrations match
the models, and packages import only from the layers below them."""

import json
import subprocess
import sys
from pathlib import Path

import psycopg
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from importlinter.cli import lint_imports
from sqlalchemy import create_engine

from job_scout import tables  # noqa: F401  # registers every table
from job_scout.config import Settings
from job_scout.db import Base
from job_scout.migrations import include_name

BACKEND = Path(__file__).parents[1]


def test_job_scout_tables_registers_every_migrated_table(settings: Settings) -> None:
    # A fresh interpreter, so no other import has registered a table first
    registered = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json; from job_scout import tables; from job_scout.db import Base; "
            "print(json.dumps(sorted(Base.metadata.tables)))",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    with psycopg.connect(settings.database_url) as conn:
        migrated = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            " AND table_name <> 'alembic_version' AND table_name NOT LIKE 'procrastinate_%'"
        ).fetchall()

    assert json.loads(registered.stdout) == sorted(name for (name,) in migrated)


def test_the_migrations_match_the_models(settings: Settings) -> None:
    """What `alembic revision --autogenerate` would find to migrate: nothing."""
    engine = create_engine(settings.sqlalchemy_url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection, opts={"include_name": include_name, "compare_type": True}
            )
            assert compare_metadata(context, Base.metadata) == []
    finally:
        engine.dispose()


def test_packages_import_only_from_the_layers_below() -> None:
    """The layers contract in pyproject.toml; run `uv run lint-imports` for the details."""
    assert lint_imports(config_filename=str(BACKEND / "pyproject.toml"), no_cache=True) == 0
