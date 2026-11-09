import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from job_scout.db import Base
from job_scout.llm.interface import Provider


class ProviderKey(Base):
    """The owner's API key for one Provider, as plain text (ADR 0006). It never leaves the
    backend in full. Replacing it overwrites the row."""

    __tablename__ = "provider_keys"
    __table_args__ = (UniqueConstraint("owner_id", "provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    provider: Mapped[Provider] = mapped_column(String)
    api_key: Mapped[str]
    saved_at: Mapped[datetime]


class ModelListing(Base):
    """The models one Provider listed for the owner's key, as its filtering rules kept them:
    the cache every picker offers from, refetched once it is a day old. Each model is
    stored as `ListedModel`'s fields, less the Provider."""

    __tablename__ = "model_listings"
    __table_args__ = (UniqueConstraint("owner_id", "provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    provider: Mapped[Provider] = mapped_column(String)
    fetched_at: Mapped[datetime]
    models: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)


class HiddenModel(Base):
    """A model the owner hid: it is not offered, whether or not its Provider lists it."""

    __tablename__ = "hidden_models"
    __table_args__ = (UniqueConstraint("owner_id", "provider", "model_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    provider: Mapped[Provider] = mapped_column(String)
    model_id: Mapped[str]


class ModelOptions(Base):
    """How the owner wants models offered. Without a row, dated snapshots are left out."""

    __tablename__ = "model_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    show_snapshots: Mapped[bool]
