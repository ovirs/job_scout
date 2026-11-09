from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from job_scout.llm.interface import ListedModel, Provider
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


class OfferedModelRead(BaseModel):
    """A model a picker offers: the owner's Provider lists it for their key, and the owner
    has not hidden it."""

    provider: Provider
    id: str = Field(examples=["claude-opus-5-5"])
    display_name: str
    # Pinned to one release by a date or version in its name
    snapshot: bool
    # The effort levels it accepts, in the Provider's own names; none without an effort control
    efforts: list[str]

    @classmethod
    def of(cls, model: ListedModel) -> "OfferedModelRead":
        return cls(
            provider=model.provider,
            id=model.id,
            display_name=model.display_name,
            snapshot=model.snapshot,
            efforts=list(model.efforts),
        )


class ModelRead(OfferedModelRead):
    """A model as Settings lists it: hidden ones are listed too, to offer again."""

    hidden: bool


class ProviderModelsRead(BaseModel):
    """One Provider's models, as its listing for the owner's key holds them."""

    provider: Provider
    name: str
    # When the Provider last listed them; null if it never has
    fetched_at: datetime | None
    # Why the Provider refused to list them just now; the list from before is kept
    refused: str | None
    models: list[ModelRead]


class ModelsRead(BaseModel):
    """The models of every Provider the owner has set up, and whether dated snapshots are
    offered."""

    show_snapshots: bool
    providers: list[ProviderModelsRead]

    @classmethod
    def of(cls, models: settings.Models) -> "ModelsRead":
        return cls(
            show_snapshots=models.show_snapshots,
            providers=[
                ProviderModelsRead(
                    provider=provider.provider,
                    name=settings.PROVIDER_NAMES[provider.provider],
                    fetched_at=provider.fetched_at,
                    refused=provider.refused,
                    models=[
                        ModelRead(
                            **OfferedModelRead.of(model).model_dump(),
                            hidden=models.is_hidden(model),
                        )
                        for model in provider.models
                    ],
                )
                for provider in models.providers
            ],
        )


class ShowSnapshotsSave(BaseModel):
    show_snapshots: bool
