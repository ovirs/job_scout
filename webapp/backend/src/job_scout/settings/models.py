import uuid
from datetime import datetime

from sqlalchemy import String, UniqueConstraint
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
