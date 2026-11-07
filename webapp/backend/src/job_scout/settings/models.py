import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from job_scout.db import Base

Provider = Literal["anthropic", "openai", "google"]


class ProviderKey(Base):
    """The user's API key for one Provider, kept as typed (ADR 0006).

    An owner has at most one key per Provider; replacing it overwrites the row.
    """

    __tablename__ = "provider_keys"
    __table_args__ = (UniqueConstraint("owner_id", "provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    provider: Mapped[Provider] = mapped_column(String)
    key: Mapped[str]
    saved_at: Mapped[datetime] = mapped_column(server_default=func.now())
