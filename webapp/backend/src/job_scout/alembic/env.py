from alembic import context
from sqlalchemy import create_engine

from job_scout import tables  # noqa: F401  # registers the tables on Base.metadata
from job_scout.config import Settings
from job_scout.db import Base
from job_scout.migrations import include_name

url = context.config.attributes.get("sqlalchemy_url") or Settings().sqlalchemy_url

engine = create_engine(url)
with engine.connect() as connection:
    context.configure(
        connection=connection, target_metadata=Base.metadata, include_name=include_name
    )
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
