from datetime import datetime

from pydantic import BaseModel

from job_scout.fields import NonBlank
from job_scout.settings import domain
from job_scout.settings.models import Provider, ProviderKey


class ProviderKeySave(BaseModel):
    key: NonBlank


class ProviderRead(BaseModel):
    """A Provider and the user's key for it; never the key itself, only its masked form."""

    provider: Provider
    available: bool  # whether it has an adapter, so a key can be set up
    masked_key: str | None
    saved_at: datetime | None

    @classmethod
    def of(cls, provider: Provider, stored: ProviderKey | None) -> "ProviderRead":
        return cls(
            provider=provider,
            available=provider in domain.AVAILABLE,
            masked_key=None if stored is None else domain.mask(stored.key),
            saved_at=None if stored is None else stored.saved_at,
        )


class ProviderKeySaved(BaseModel):
    provider: ProviderRead
    models: list[str]  # what the Provider listed with the key


class SetupStatus(BaseModel):
    has_provider: bool
