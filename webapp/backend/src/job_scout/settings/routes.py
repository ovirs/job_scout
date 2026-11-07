from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from job_scout.routing import Owner, Session
from job_scout.settings import domain as settings
from job_scout.settings.domain import ModelLister
from job_scout.settings.models import Provider
from job_scout.settings.schemas import ProviderKeySave, ProviderKeySaved, ProviderRead, SetupStatus

router = APIRouter(prefix="/api")


def get_model_lister(request: Request) -> ModelLister:
    lister: ModelLister = request.app.state.model_lister
    return lister


Lister = Annotated[ModelLister, Depends(get_model_lister)]


@router.get("/setup")
async def get_setup_status(session: Session, owner: Owner) -> SetupStatus:
    """Whether the user has a Provider; until they do, the app shows only its setup screen
    and every endpoint that starts an LLM run refuses."""
    return SetupStatus(has_provider=await settings.has_provider(session, owner_id=owner))


@router.get("/settings/providers")
async def list_providers(session: Session, owner: Owner) -> list[ProviderRead]:
    """Every Provider, with the user's key for it masked, if they have one."""
    stored = {key.provider: key for key in await settings.keys(session, owner_id=owner)}
    return [ProviderRead.of(provider, stored.get(provider)) for provider in settings.PROVIDERS]


@router.put("/settings/providers/{provider}")
async def save_provider_key(
    provider: Provider, body: ProviderKeySave, session: Session, owner: Owner, lister: Lister
) -> ProviderKeySaved:
    """Save, or replace, the key for a Provider. The key is checked by listing the Provider's
    models with it, which are returned; a key the Provider refuses is not saved, and 422
    returns the Provider's reason. Only available Providers can be set up."""
    with _refusals():
        stored, models = await settings.save_key(
            session, lister, owner_id=owner, provider=provider, key=body.key
        )
    await session.commit()
    return ProviderKeySaved(provider=ProviderRead.of(provider, stored), models=models)


@router.delete("/settings/providers/{provider}", status_code=204)
async def remove_provider_key(provider: Provider, session: Session, owner: Owner) -> None:
    """Remove the key for a Provider. Removing the last one returns the app to its setup
    screen."""
    with _refusals():
        await settings.remove_key(session, owner_id=owner, provider=provider)
    await session.commit()


@contextmanager
def _refusals() -> Iterator[None]:
    """Map the Settings package's errors to HTTP."""
    try:
        yield
    except settings.ListingRefused as refusal:
        raise HTTPException(status_code=422, detail=str(refusal)) from None
    except settings.NotAvailable as refusal:
        raise HTTPException(status_code=409, detail=str(refusal)) from None
    except settings.NoSuchKey as refusal:
        raise HTTPException(status_code=404, detail=str(refusal)) from None
