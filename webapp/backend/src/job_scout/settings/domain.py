"""Settings: how the owner has set the app up to run. For now, their Provider keys.

A key is checked before it is saved: the Provider must list its models with it. The app
is set up once the owner has a key for at least one Provider; until then nothing that
calls an LLM may start.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_scout.llm.interface import KeyRefused, ModelLister, Provider
from job_scout.settings.models import ProviderKey

PROVIDER_NAMES: dict[Provider, str] = {
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "google": "Google",
}


class NotAvailable(Exception):
    """The Provider has no adapter yet, so it cannot be set up."""


class Refused(Exception):
    """The Provider refused the key; the message is its reason."""


class NoSuchKey(Exception):
    """The owner has no key for the Provider."""


class NoProvider(Exception):
    """The owner has no Provider set up, so no LLM run can start."""


async def keys(session: AsyncSession, *, owner_id: uuid.UUID) -> dict[Provider, ProviderKey]:
    """The owner's keys, by Provider."""
    found = await session.scalars(select(ProviderKey).where(ProviderKey.owner_id == owner_id))
    return {key.provider: key for key in found}


async def api_key(session: AsyncSession, *, owner_id: uuid.UUID, provider: Provider) -> str | None:
    """The owner's key for the Provider, in full, for calling it; None without one."""
    return await session.scalar(
        select(ProviderKey.api_key).where(
            ProviderKey.owner_id == owner_id, ProviderKey.provider == provider
        )
    )


async def has_provider(session: AsyncSession, *, owner_id: uuid.UUID) -> bool:
    """Whether the owner has a key for at least one Provider; a key is only ever saved for
    an available one."""
    found = await session.scalar(
        select(ProviderKey.id).where(ProviderKey.owner_id == owner_id).limit(1)
    )
    return found is not None


async def require_provider(session: AsyncSession, *, owner_id: uuid.UUID) -> None:
    """Raises `NoProvider` while the owner has no Provider set up."""
    if not await has_provider(session, owner_id=owner_id):
        raise NoProvider("Set up a Provider in Settings before running the LLM")


async def save_key(
    session: AsyncSession,
    lister: ModelLister,
    *,
    owner_id: uuid.UUID,
    provider: Provider,
    api_key: str,
) -> ProviderKey:
    """Save the owner's key for the Provider, replacing any earlier one, committed, once
    the Provider lists its models with it. Raises `NotAvailable` for a Provider with no
    adapter, and `Refused`, saving nothing, when the Provider refuses the key."""
    if provider not in lister.available:
        raise NotAvailable(f"{PROVIDER_NAMES[provider]} is not available yet")
    listing = await lister.list_models(provider, api_key)
    if isinstance(listing, KeyRefused):
        raise Refused(f"{PROVIDER_NAMES[provider]} refused the key: {listing.reason}")
    key = (await keys(session, owner_id=owner_id)).get(provider)
    if key is None:
        key = ProviderKey(owner_id=owner_id, provider=provider)
        session.add(key)
    key.api_key = api_key
    key.saved_at = datetime.now(UTC)
    await session.commit()
    return key


async def remove_key(session: AsyncSession, *, owner_id: uuid.UUID, provider: Provider) -> None:
    """Delete the owner's key for the Provider, committed. Raises `NoSuchKey`."""
    key = (await keys(session, owner_id=owner_id)).get(provider)
    if key is None:
        raise NoSuchKey
    await session.delete(key)
    await session.commit()


def masked(api_key: str) -> str:
    """The key as it may be shown: its first three and last four characters, or nothing of
    a key too short to keep the rest hidden."""
    if len(api_key) < 12:
        return "…"
    return f"{api_key[:3]}…{api_key[-4:]}"
