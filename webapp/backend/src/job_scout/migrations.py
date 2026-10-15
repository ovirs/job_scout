"""Database migrations (Alembic). Apply with `python -m job_scout.migrations`."""

from pathlib import Path

from alembic import command
from alembic.config import Config

from job_scout.config import Settings


def upgrade(database_url: str) -> None:
    command.upgrade(_config(Settings(database_url=database_url)), "head")


def _config(settings: Settings) -> Config:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "alembic"))
    config.attributes["sqlalchemy_url"] = settings.sqlalchemy_url
    return config


if __name__ == "__main__":
    upgrade(Settings().database_url)
