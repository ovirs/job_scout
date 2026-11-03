from fastapi import APIRouter, HTTPException

from job_scout.routing import Owner, Session
from job_scout.user_inputs import domain as user_inputs
from job_scout.user_inputs.models import DocumentKind
from job_scout.user_inputs.schemas import (
    DealBreakerSave,
    DealBreakerSetVersionRead,
    DocumentSave,
    DocumentVersionRead,
)

router = APIRouter(prefix="/api")


@router.get("/documents/{kind}")
async def get_current_document(
    kind: DocumentKind, session: Session, owner: Owner
) -> DocumentVersionRead | None:
    """The current version of a document, or null while the user has not written it."""
    version = await user_inputs.current_document(session, owner_id=owner, kind=kind)
    return None if version is None else DocumentVersionRead.of(version)


@router.post("/documents/{kind}/versions", status_code=201)
async def save_document(
    kind: DocumentKind, body: DocumentSave, session: Session, owner: Owner
) -> DocumentVersionRead:
    version = await user_inputs.save_document(session, owner_id=owner, kind=kind, text=body.text)
    await session.commit()
    return DocumentVersionRead.of(version)


@router.get("/documents/{kind}/versions/{version_id}")
async def get_document_version(
    kind: DocumentKind, version_id: int, session: Session, owner: Owner
) -> DocumentVersionRead:
    version = await user_inputs.document_version(
        session, owner_id=owner, kind=kind, version_id=version_id
    )
    if version is None:
        raise HTTPException(status_code=404, detail="No such document version")
    return DocumentVersionRead.of(version)


@router.get("/deal-breakers")
async def get_current_deal_breakers(
    session: Session, owner: Owner
) -> DealBreakerSetVersionRead | None:
    """The current set of Deal Breakers, or null while the user has added none."""
    version = await user_inputs.current_deal_breaker_set(session, owner_id=owner)
    return None if version is None else DealBreakerSetVersionRead.of(version)


@router.post("/deal-breakers", status_code=201)
async def add_deal_breaker(
    body: DealBreakerSave, session: Session, owner: Owner
) -> DealBreakerSetVersionRead:
    """Add a Deal Breaker; returns the new version of the set."""
    version = await user_inputs.add_deal_breaker(session, owner_id=owner, text=body.text)
    await session.commit()
    return DealBreakerSetVersionRead.of(version)


@router.put("/deal-breakers/{deal_breaker_id}")
async def edit_deal_breaker(
    deal_breaker_id: int, body: DealBreakerSave, session: Session, owner: Owner
) -> DealBreakerSetVersionRead:
    """Change a Deal Breaker's text, keeping its id; returns the new version of the set."""
    version = await user_inputs.edit_deal_breaker(
        session, owner_id=owner, deal_breaker_id=deal_breaker_id, text=body.text
    )
    if version is None:
        raise HTTPException(status_code=404, detail="No such Deal Breaker")
    await session.commit()
    return DealBreakerSetVersionRead.of(version)


@router.delete("/deal-breakers/{deal_breaker_id}")
async def delete_deal_breaker(
    deal_breaker_id: int, session: Session, owner: Owner
) -> DealBreakerSetVersionRead:
    """Delete a Deal Breaker; returns the new version of the set, without it."""
    version = await user_inputs.delete_deal_breaker(
        session, owner_id=owner, deal_breaker_id=deal_breaker_id
    )
    if version is None:
        raise HTTPException(status_code=404, detail="No such Deal Breaker")
    await session.commit()
    return DealBreakerSetVersionRead.of(version)


@router.get("/deal-breakers/versions/{version_id}")
async def get_deal_breaker_set_version(
    version_id: int, session: Session, owner: Owner
) -> DealBreakerSetVersionRead:
    version = await user_inputs.deal_breaker_set_version(
        session, owner_id=owner, version_id=version_id
    )
    if version is None:
        raise HTTPException(status_code=404, detail="No such version of the Deal Breakers")
    return DealBreakerSetVersionRead.of(version)
