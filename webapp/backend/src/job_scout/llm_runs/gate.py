"""The setup gate for routes that start an LLM run: refused while the user has no Provider."""

from fastapi import Depends, HTTPException

from job_scout.routing import Owner, Session
from job_scout.settings import domain as settings


async def require_provider(session: Session, owner: Owner) -> None:
    if not await settings.has_provider(session, owner_id=owner):
        raise HTTPException(
            status_code=409,
            detail="Add a Provider key in Settings first: no LLM call can be made without one",
        )


# A route's `dependencies`: it starts an LLM run, so it needs a Provider
NEEDS_PROVIDER = [Depends(require_provider)]
