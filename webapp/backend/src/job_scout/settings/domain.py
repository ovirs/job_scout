"""The user's settings: the Providers they have a key for.

A Provider is an LLM vendor. Only those with an adapter are available, so only they
can be set up. The owner "has a Provider" once they have a key for an available one;
until then the app is gated (see `llm_runs.gate`), and the worker reads the key afresh
for every attempt of a run.
"""

import uuid
from datetime import UTC, datetime
from typing import Protocol, get_args

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_scout.settings.models import Provider, ProviderKey

PROVIDERS: tuple[Provider, ...] = get_args(Provider)

# The Providers with an adapter, in the order the worker prefers them
AVAILABLE: tuple[Provider, ...] = ("anthropic",)


class ListingRefused(Exception):
    """The Provider refused to list its models with the key; the message is its reason."""


class NotAvailable(Exception):
    """The Provider has no adapter yet, so no key can be set up for it."""


class NoSuchKey(Exception):
    """The owner has no key for the Provider."""


class ModelLister(Protocol):
    """Lists a Provider's models with a key: how a key is checked when it is saved."""

    async def list_models(self, provider: Provider, api_key: str) -> list[str]:
        """The ids of the Provider's models; raises `ListingRefused` with the Provider's
        reason when the key is refused or the Provider cannot be reached."""
        ...


def mask(key: str) -> str:
    """The key with all but its last four characters hidden; a short key is hidden whole."""
    return "•" * 8 + key[-4:] if len(key) > 12 else "•" * 8


async def keys(session: AsyncSession, *, owner_id: uuid.UUID) -> list[ProviderKey]:
    result = await session.scalars(select(ProviderKey).where(ProviderKey.owner_id == owner_id))
    return list(result)


async def save_key(
    session: AsyncSession,
    lister: ModelLister,
    *,
    owner_id: uuid.UUID,
    provider: Provider,
    key: str,
) -> tuple[ProviderKey, list[str]]:
    """Check the key by listing the Provider's models with it, then store it, replacing any
    earlier one. A refused key is not stored: `ListingRefused`. The caller commits."""
    if provider not in AVAILABLE:
        raise NotAvailable(f"{provider} is not available yet")
    models = await lister.list_models(provider, key)
    stored = await _key(session, owner_id, provider)
    if stored is None:
        stored = ProviderKey(owner_id=owner_id, provider=provider, key=key)
        session.add(stored)
    stored.key = key
    stored.saved_at = datetime.now(UTC)
    await session.flush()
    return stored, models


async def remove_key(session: AsyncSession, *, owner_id: uuid.UUID, provider: Provider) -> None:
    """Remove the owner's key for the Provider; the caller commits."""
    stored = await _key(session, owner_id, provider)
    if stored is None:
        raise NoSuchKey(f"No {provider} key to remove")
    await session.delete(stored)
    await session.flush()


async def active_key(session: AsyncSession, *, owner_id: uuid.UUID) -> str | None:
    """The key the owner's runs use: that of their first available Provider; None while they
    have no Provider."""
    stored = {key.provider: key.key for key in await keys(session, owner_id=owner_id)}
    return next((stored[provider] for provider in AVAILABLE if provider in stored), None)


async def has_provider(session: AsyncSession, *, owner_id: uuid.UUID) -> bool:
    return await active_key(session, owner_id=owner_id) is not None


async def _key(
    session: AsyncSession, owner_id: uuid.UUID, provider: Provider
) -> ProviderKey | None:
    return await session.scalar(
        select(ProviderKey).where(
            ProviderKey.owner_id == owner_id, ProviderKey.provider == provider
        )
    )
