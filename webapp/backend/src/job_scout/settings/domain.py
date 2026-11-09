"""Settings: how the owner has set the app up to run. For now, their Provider keys and the
models offered with them.

A key is checked before it is saved: the Provider must list its models with it. The app
is set up once the owner has a key for at least one Provider; until then nothing that
calls an LLM may start.

The models listed with a key are cached for a day, then fetched again; the owner can
also refresh them at once. Every picker offers the cached models less the ones the owner
hid, and less dated snapshots unless the owner shows them. A run may use only a model
that is offered.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from job_scout.llm.interface import KeyRefused, ListedModel, ModelLister, Provider
from job_scout.settings.models import HiddenModel, ModelListing, ModelOptions, ProviderKey

PROVIDER_NAMES: dict[Provider, str] = {
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "google": "Google",
}

# How long a Provider's listing of models is cached before it is fetched again
LISTING_KEPT_FOR = timedelta(days=1)


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
    stored = (await _listings(session, owner_id=owner_id)).get(provider)
    _store_listing(session, stored, owner_id=owner_id, provider=provider, listing=listing)
    await session.commit()
    return key


async def remove_key(session: AsyncSession, *, owner_id: uuid.UUID, provider: Provider) -> None:
    """Delete the owner's key for the Provider, and its cached listing, committed. Raises
    `NoSuchKey`."""
    key = (await keys(session, owner_id=owner_id)).get(provider)
    if key is None:
        raise NoSuchKey
    await session.delete(key)
    stored = (await _listings(session, owner_id=owner_id)).get(provider)
    if stored is not None:
        await session.delete(stored)
    await session.commit()


@dataclass(frozen=True)
class ProviderModels:
    """One Provider's models for the owner: the ones its listing for their key holds, less
    dated snapshots unless the owner shows them."""

    provider: Provider
    fetched_at: datetime | None  # None while the Provider has never listed them
    models: list[ListedModel]
    # Why the Provider refused to list them just now; the list fetched before is kept
    refused: str | None = None


@dataclass(frozen=True)
class Models:
    """The models of every Provider the owner has set up, and how the owner has them offered."""

    show_snapshots: bool
    hidden: frozenset[tuple[Provider, str]]
    providers: list[ProviderModels]

    def is_hidden(self, model: ListedModel) -> bool:
        return (model.provider, model.id) in self.hidden

    def offered(self) -> list[ListedModel]:
        """The models every picker offers: the ones listed and not hidden."""
        return [
            model
            for provider in self.providers
            for model in provider.models
            if not self.is_hidden(model)
        ]


async def models(
    session: AsyncSession, lister: ModelLister, *, owner_id: uuid.UUID, refresh: bool = False
) -> Models:
    """The owner's models, per Provider set up. A Provider's listing is fetched anew, and
    cached, committed, once it is a day old, and for every Provider on `refresh`."""
    return await _models(session, lister, owner_id=owner_id, fetch="all" if refresh else "stale")


async def offered(
    session: AsyncSession, lister: ModelLister, *, owner_id: uuid.UUID
) -> list[ListedModel]:
    """The models every picker offers the owner."""
    return (await models(session, lister, owner_id=owner_id)).offered()


async def usable(
    session: AsyncSession,
    lister: ModelLister,
    *,
    owner_id: uuid.UUID,
    provider: Provider,
    model_id: str,
) -> bool:
    """Whether a run may use the model: its Provider is available and the owner has a key
    for it, and the model is offered from the cached listing. Never fetches a listing."""
    cached = await _models(session, lister, owner_id=owner_id, fetch="never")
    return any(model.provider == provider and model.id == model_id for model in cached.offered())


async def show_snapshots(session: AsyncSession, *, owner_id: uuid.UUID, show: bool) -> None:
    """Offer dated snapshots, or stop offering them, committed."""
    options = await _options(session, owner_id=owner_id)
    if options is None:
        options = ModelOptions(owner_id=owner_id)
        session.add(options)
    options.show_snapshots = show
    await session.commit()


async def hide_model(
    session: AsyncSession, *, owner_id: uuid.UUID, provider: Provider, model_id: str
) -> None:
    """Stop offering the model, committed; hiding a hidden model changes nothing."""
    await session.execute(
        insert(HiddenModel)
        .values(owner_id=owner_id, provider=provider, model_id=model_id)
        .on_conflict_do_nothing()
    )
    await session.commit()


async def unhide_model(
    session: AsyncSession, *, owner_id: uuid.UUID, provider: Provider, model_id: str
) -> None:
    """Offer the hidden model again, committed; a model not hidden is left as it is."""
    await session.execute(
        delete(HiddenModel).where(
            HiddenModel.owner_id == owner_id,
            HiddenModel.provider == provider,
            HiddenModel.model_id == model_id,
        )
    )
    await session.commit()


async def _models(
    session: AsyncSession,
    lister: ModelLister,
    *,
    owner_id: uuid.UUID,
    fetch: Literal["never", "stale", "all"],
) -> Models:
    owner_keys = await keys(session, owner_id=owner_id)
    listings = await _listings(session, owner_id=owner_id)
    options = await _options(session, owner_id=owner_id)
    shows_snapshots = options is not None and options.show_snapshots
    hidden = await session.execute(
        select(HiddenModel.provider, HiddenModel.model_id).where(HiddenModel.owner_id == owner_id)
    )
    providers = []
    for provider in lister.available:
        key = owner_keys.get(provider)
        if key is None:
            continue
        stored = listings.get(provider)
        refused = None
        if fetch == "all" or (fetch == "stale" and (stored is None or _is_stale(stored))):
            listing = await lister.list_models(provider, key.api_key)
            if isinstance(listing, KeyRefused):
                refused = f"{PROVIDER_NAMES[provider]} refused the key: {listing.reason}"
            else:
                stored = _store_listing(
                    session, stored, owner_id=owner_id, provider=provider, listing=listing
                )
        providers.append(
            ProviderModels(
                provider=provider,
                fetched_at=None if stored is None else stored.fetched_at,
                models=[
                    model
                    for model in ([] if stored is None else _listed(stored))
                    if shows_snapshots or not model.snapshot
                ],
                refused=refused,
            )
        )
    if fetch != "never":
        await session.commit()
    return Models(
        show_snapshots=shows_snapshots,
        hidden=frozenset((provider, model_id) for provider, model_id in hidden),
        providers=providers,
    )


async def _options(session: AsyncSession, *, owner_id: uuid.UUID) -> ModelOptions | None:
    return await session.scalar(select(ModelOptions).where(ModelOptions.owner_id == owner_id))


async def _listings(session: AsyncSession, *, owner_id: uuid.UUID) -> dict[Provider, ModelListing]:
    found = await session.scalars(select(ModelListing).where(ModelListing.owner_id == owner_id))
    return {listing.provider: listing for listing in found}


def _is_stale(listing: ModelListing) -> bool:
    return datetime.now(UTC) - listing.fetched_at >= LISTING_KEPT_FOR


def _store_listing(
    session: AsyncSession,
    stored: ModelListing | None,
    *,
    owner_id: uuid.UUID,
    provider: Provider,
    listing: list[ListedModel],
) -> ModelListing:
    """Cache the models the Provider listed for the owner's key, in place of `stored`."""
    if stored is None:
        stored = ModelListing(owner_id=owner_id, provider=provider)
        session.add(stored)
    stored.fetched_at = datetime.now(UTC)
    stored.models = [
        {
            "id": model.id,
            "display_name": model.display_name,
            "snapshot": model.snapshot,
            "efforts": list(model.efforts),
        }
        for model in listing
    ]
    return stored


def _listed(listing: ModelListing) -> list[ListedModel]:
    return [
        ListedModel(
            provider=listing.provider,
            id=model["id"],
            display_name=model["display_name"],
            snapshot=model["snapshot"],
            efforts=tuple(model["efforts"]),
        )
        for model in listing.models
    ]


def masked(api_key: str) -> str:
    """The key as it may be shown: its first three and last four characters, or nothing of
    a key too short to keep the rest hidden."""
    if len(api_key) < 12:
        return "…"
    return f"{api_key[:3]}…{api_key[-4:]}"
