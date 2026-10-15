from alembic import context
from sqlalchemy import create_engine

from job_scout import models  # noqa: F401  # registers the tables on Base.metadata
from job_scout.config import Settings
from job_scout.db import Base

url = context.config.attributes.get("sqlalchemy_url") or Settings().sqlalchemy_url


def include_name(name: str | None, type_: str, parent_names: object) -> bool:
    # Procrastinate's tables come from its own vendored schema, not from our models
    return not (type_ == "table" and name is not None and name.startswith("procrastinate_"))


engine = create_engine(url)
with engine.connect() as connection:
    context.configure(
        connection=connection, target_metadata=Base.metadata, include_name=include_name
    )
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
