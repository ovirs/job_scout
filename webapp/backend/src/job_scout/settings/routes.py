from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import APIRouter, Depends, HTTPException

from job_scout.llm.interface import PROVIDERS, Provider
from job_scout.routing import Lister, Owner, Session
from job_scout.settings import domain as settings
from job_scout.settings.schemas import (
    DefaultRead,
    DefaultsSave,
    ModelsRead,
    OfferedModelRead,
    ProviderKeySave,
    ProviderRead,
    SetupRead,
    ShowSnapshotsSave,
)

router = APIRouter(prefix="/api")


@router.get("/setup")
async def get_setup(session: Session, owner: Owner) -> SetupRead:
    """Whether the owner has set up a Provider, and a default model for every step; until
    they have both, the app shows only the setup screen."""
    return SetupRead(
        has_provider=await settings.has_provider(session, owner_id=owner),
        has_defaults=await settings.has_defaults(session, owner_id=owner),
    )


@router.get("/settings/providers")
async def list_providers(session: Session, lister: Lister, owner: Owner) -> list[ProviderRead]:
    """Every Provider, whether it can be set up yet, and the owner's key for it, masked."""
    keys = await settings.keys(session, owner_id=owner)
    return [
        ProviderRead.of(provider, keys.get(provider), available=provider in lister.available)
        for provider in PROVIDERS
    ]


@router.put("/settings/providers/{provider}/key")
async def save_provider_key(
    provider: Provider, body: ProviderKeySave, session: Session, lister: Lister, owner: Owner
) -> ProviderRead:
    """Save the owner's key for the Provider, replacing any earlier one; it takes effect on
    the next LLM call. Checked first by listing the Provider's models with it: a refused
    key is not saved, and the Provider's reason is returned. Refused for a Provider that
    is not available yet."""
    with _refusals():
        key = await settings.save_key(
            session, lister, owner_id=owner, provider=provider, api_key=body.api_key
        )
    return ProviderRead.of(provider, key, available=True)


@router.delete("/settings/providers/{provider}/key", status_code=204)
async def remove_provider_key(provider: Provider, session: Session, owner: Owner) -> None:
    """Remove the owner's key for the Provider. Removing the last one returns the app to
    the setup screen."""
    with _refusals():
        await settings.remove_key(session, owner_id=owner, provider=provider)


@router.get("/models")
async def list_offered_models(
    session: Session, lister: Lister, owner: Owner
) -> list[OfferedModelRead]:
    """The models every picker offers: each Provider's listing for the owner's key, less
    the models the owner hid, and less dated snapshots unless the owner shows them. A
    listing is fetched again once it is a day old."""
    offered = await settings.offered(session, lister, owner_id=owner)
    return [OfferedModelRead.of(model) for model in offered]


@router.get("/settings/models")
async def list_models(session: Session, lister: Lister, owner: Owner) -> ModelsRead:
    """Each Provider's models for the owner's key, hidden ones included, and whether dated
    snapshots are offered. A listing is fetched again once it is a day old."""
    return ModelsRead.of(await settings.models(session, lister, owner_id=owner))


@router.post("/settings/models/refresh")
async def refresh_models(session: Session, lister: Lister, owner: Owner) -> ModelsRead:
    """Fetch every Provider's listing again now, as `list_models` returns it. A Provider
    that refuses keeps the list it gave before, with its reason."""
    return ModelsRead.of(await settings.models(session, lister, owner_id=owner, refresh=True))


@router.put("/settings/show-snapshots", status_code=204)
async def save_show_snapshots(body: ShowSnapshotsSave, session: Session, owner: Owner) -> None:
    """Offer dated snapshots, such as `gpt-5-2025-08-07`, in every picker, or stop."""
    await settings.show_snapshots(session, owner_id=owner, show=body.show_snapshots)


@router.put("/settings/hidden-models/{provider}/{model_id}", status_code=204)
async def hide_model(provider: Provider, model_id: str, session: Session, owner: Owner) -> None:
    """Hide the model from every picker; a hidden model cannot be used."""
    await settings.hide_model(session, owner_id=owner, provider=provider, model_id=model_id)


@router.delete("/settings/hidden-models/{provider}/{model_id}", status_code=204)
async def unhide_model(provider: Provider, model_id: str, session: Session, owner: Owner) -> None:
    """Offer the hidden model again."""
    await settings.unhide_model(session, owner_id=owner, provider=provider, model_id=model_id)


@router.get("/settings/defaults")
async def list_defaults(session: Session, lister: Lister, owner: Owner) -> list[DefaultRead]:
    """Each step's default model choice, which its runs take when queued, and why a run
    cannot take it now, if it cannot: its Provider's key is gone, or its model is hidden or
    no longer listed. Read from the cached listing."""
    found = await settings.defaults(session, lister, owner_id=owner)
    return [DefaultRead.of(default) for default in found]


@router.put("/settings/defaults", status_code=204)
async def save_defaults(body: DefaultsSave, session: Session, lister: Lister, owner: Owner) -> None:
    """Make each choice given its step's default; a step left out keeps its own. Refused,
    saving none, when one is not offered, or its model does not take its effort."""
    with _refusals():
        await settings.save_defaults(session, lister, owner_id=owner, choices=body.choices())


async def require_set_up(session: Session, owner: Owner) -> None:
    """For any route that starts an LLM run: a 409 while the owner has no Provider, or a
    step has no default."""
    with _refusals():
        await settings.require_set_up(session, owner_id=owner)


# Add to a route that starts an LLM run, as `dependencies=[SET_UP]`
SET_UP = Depends(require_set_up)


@contextmanager
def _refusals() -> Iterator[None]:
    """Map the Settings package's errors to HTTP."""
    try:
        yield
    except settings.NoSuchKey:
        raise HTTPException(status_code=404, detail="No key for this Provider") from None
    except (settings.Refused, settings.NotUsable) as refusal:
        raise HTTPException(status_code=422, detail=str(refusal)) from None
    except (settings.NotAvailable, settings.NoProvider, settings.NoDefaults) as refusal:
        raise HTTPException(status_code=409, detail=str(refusal)) from None
