"""Database migrations (Alembic). Apply with `python -m job_scout.migrations`."""

from pathlib import Path

from alembic import command
from alembic.config import Config

from job_scout.config import Settings


def upgrade(database_url: str) -> None:
    command.upgrade(_config(Settings(database_url=database_url)), "head")


def include_name(name: str | None, type_: str, parent_names: object) -> bool:
    """Whether Alembic compares a database object with the models."""
    # Procrastinate's tables come from its own vendored schema, not from our models
    return not (type_ == "table" and name is not None and name.startswith("procrastinate_"))


def _config(settings: Settings) -> Config:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "alembic"))
    config.attributes["sqlalchemy_url"] = settings.sqlalchemy_url
    return config


if __name__ == "__main__":
    upgrade(Settings().database_url)
