from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from job_scout.llm.interface import Provider
from job_scout.settings import domain as settings
from job_scout.settings.models import ProviderKey


class ProviderKeySave(BaseModel):
    # Surrounding whitespace, as a paste often brings, is dropped
    api_key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ProviderKeyRead(BaseModel):
    """A stored key, never in full."""

    masked: str = Field(examples=["sk-…a1b2"])
    saved_at: datetime

    @classmethod
    def of(cls, key: ProviderKey) -> "ProviderKeyRead":
        return cls(masked=settings.masked(key.api_key), saved_at=key.saved_at)


class ProviderRead(BaseModel):
    """A Provider: whether it can be set up yet (it has an adapter), and the owner's key."""

    provider: Provider
    name: str
    available: bool
    key: ProviderKeyRead | None

    @classmethod
    def of(cls, provider: Provider, key: ProviderKey | None, *, available: bool) -> "ProviderRead":
        return cls(
            provider=provider,
            name=settings.PROVIDER_NAMES[provider],
            available=available,
            key=None if key is None else ProviderKeyRead.of(key),
        )


class SetupRead(BaseModel):
    """Whether the app is set up: until it is, the UI shows only the setup screen."""

    has_provider: bool
