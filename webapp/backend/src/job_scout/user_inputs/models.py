import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from job_scout.db import Base

DocumentKind = Literal["career-profile", "preferences", "writing-guide"]


class DocumentVersion(Base):
    """One saved version of a Career Profile, Preferences or Writing Guide.

    Saving a document adds a version; a version is never changed afterwards.
    The current version of a document is the one with the highest number.
    """

    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("owner_id", "kind", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    kind: Mapped[DocumentKind] = mapped_column(String)
    number: Mapped[int]  # 1, 2, 3, ... per owner and kind
    text: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class DealBreaker(Base):
    """A Deal Breaker's identity, stable across versions of the set.

    Its text lives in the set versions, so editing it keeps its id. Deleting
    it only stamps `deleted_at` and leaves it out of the next version of the set.
    """

    __tablename__ = "deal_breakers"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    deleted_at: Mapped[datetime | None]


class DealBreakerSetVersion(Base):
    """One version of the user's Deal Breakers, versioned as a set.

    Adding, editing or deleting a Deal Breaker adds a version; a version is
    never changed afterwards. The current set is the one with the highest number.
    """

    __tablename__ = "deal_breaker_set_versions"
    __table_args__ = (UniqueConstraint("owner_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    number: Mapped[int]  # 1, 2, 3, ... per owner
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    items: Mapped[list["DealBreakerSetItem"]] = relationship(
        order_by="DealBreakerSetItem.deal_breaker_id", lazy="selectin"
    )


class DealBreakerSetItem(Base):
    """The text of one Deal Breaker in one version of the set."""

    __tablename__ = "deal_breaker_set_items"

    set_version_id: Mapped[int] = mapped_column(
        ForeignKey("deal_breaker_set_versions.id"), primary_key=True
    )
    deal_breaker_id: Mapped[int] = mapped_column(ForeignKey("deal_breakers.id"), primary_key=True)
    text: Mapped[str]
