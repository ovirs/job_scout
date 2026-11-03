"""The four inputs the user writes: Career Profile, Preferences, Writing Guide and Deal Breakers.

Every save adds a new immutable version, so later records can name the exact
versions they used. Saving never triggers an Evaluation or any other LLM call.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_scout.user_inputs.models import (
    DealBreaker,
    DealBreakerSetItem,
    DealBreakerSetVersion,
    DocumentKind,
    DocumentVersion,
)


async def save_document(
    session: AsyncSession, *, owner_id: uuid.UUID, kind: DocumentKind, text: str
) -> DocumentVersion:
    current = await current_document(session, owner_id=owner_id, kind=kind)
    version = DocumentVersion(
        owner_id=owner_id,
        kind=kind,
        number=_next_number(current),
        text=text,
    )
    session.add(version)
    return version


async def current_document(
    session: AsyncSession, *, owner_id: uuid.UUID, kind: DocumentKind
) -> DocumentVersion | None:
    return await session.scalar(
        select(DocumentVersion)
        .where(DocumentVersion.owner_id == owner_id, DocumentVersion.kind == kind)
        .order_by(DocumentVersion.number.desc())
        .limit(1)
    )


async def document_version(
    session: AsyncSession, *, owner_id: uuid.UUID, kind: DocumentKind, version_id: int
) -> DocumentVersion | None:
    return await session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.id == version_id,
            DocumentVersion.owner_id == owner_id,
            DocumentVersion.kind == kind,
        )
    )


async def add_deal_breaker(
    session: AsyncSession, *, owner_id: uuid.UUID, text: str
) -> DealBreakerSetVersion:
    deal_breaker = DealBreaker(owner_id=owner_id)
    session.add(deal_breaker)
    await session.flush()  # assigns the new Deal Breaker's id
    current = await current_deal_breaker_set(session, owner_id=owner_id)
    texts = {**_texts_by_id(current), deal_breaker.id: text}
    return _add_deal_breaker_set(session, owner_id=owner_id, previous=current, texts=texts)


async def edit_deal_breaker(
    session: AsyncSession, *, owner_id: uuid.UUID, deal_breaker_id: int, text: str
) -> DealBreakerSetVersion | None:
    """Change one Deal Breaker's text, keeping its id; None if it is not in the current set."""
    current = await current_deal_breaker_set(session, owner_id=owner_id)
    texts = _texts_by_id(current)
    if deal_breaker_id not in texts:
        return None
    texts[deal_breaker_id] = text
    return _add_deal_breaker_set(session, owner_id=owner_id, previous=current, texts=texts)


async def delete_deal_breaker(
    session: AsyncSession, *, owner_id: uuid.UUID, deal_breaker_id: int
) -> DealBreakerSetVersion | None:
    """Soft-delete a Deal Breaker: it leaves the set but stays in earlier versions.

    None if it is not in the current set.
    """
    current = await current_deal_breaker_set(session, owner_id=owner_id)
    texts = _texts_by_id(current)
    if deal_breaker_id not in texts:
        return None
    deal_breaker = await session.get_one(DealBreaker, deal_breaker_id)
    deal_breaker.deleted_at = datetime.now(UTC)
    del texts[deal_breaker_id]
    return _add_deal_breaker_set(session, owner_id=owner_id, previous=current, texts=texts)


async def current_deal_breaker_set(
    session: AsyncSession, *, owner_id: uuid.UUID
) -> DealBreakerSetVersion | None:
    return await session.scalar(
        select(DealBreakerSetVersion)
        .where(DealBreakerSetVersion.owner_id == owner_id)
        .order_by(DealBreakerSetVersion.number.desc())
        .limit(1)
    )


async def deal_breaker_set_version(
    session: AsyncSession, *, owner_id: uuid.UUID, version_id: int
) -> DealBreakerSetVersion | None:
    return await session.scalar(
        select(DealBreakerSetVersion).where(
            DealBreakerSetVersion.id == version_id, DealBreakerSetVersion.owner_id == owner_id
        )
    )


def _texts_by_id(version: DealBreakerSetVersion | None) -> dict[int, str]:
    """A version of the set, as each Deal Breaker's text by its id."""
    return {} if version is None else {item.deal_breaker_id: item.text for item in version.items}


def _add_deal_breaker_set(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    previous: DealBreakerSetVersion | None,
    texts: dict[int, str],
) -> DealBreakerSetVersion:
    version = DealBreakerSetVersion(
        owner_id=owner_id,
        number=_next_number(previous),
        items=[
            DealBreakerSetItem(deal_breaker_id=deal_breaker_id, text=text)
            for deal_breaker_id, text in texts.items()
        ],
    )
    session.add(version)
    return version


def _next_number(current: DocumentVersion | DealBreakerSetVersion | None) -> int:
    return 1 if current is None else current.number + 1
