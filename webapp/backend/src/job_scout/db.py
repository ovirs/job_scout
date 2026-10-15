from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from job_scout.config import Settings


class Base(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True)}


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(settings.sqlalchemy_url)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
