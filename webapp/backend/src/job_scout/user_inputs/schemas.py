from datetime import datetime

from pydantic import BaseModel

from job_scout.fields import NonBlank
from job_scout.user_inputs.models import DealBreakerSetVersion, DocumentKind, DocumentVersion


class DocumentSave(BaseModel):
    # Blank is allowed: it clears the document. Whether it is required is Evaluation's concern.
    text: str


class DocumentVersionRead(BaseModel):
    id: int
    kind: DocumentKind
    number: int
    text: str
    created_at: datetime

    @classmethod
    def of(cls, version: DocumentVersion) -> "DocumentVersionRead":
        return cls(
            id=version.id,
            kind=version.kind,
            number=version.number,
            text=version.text,
            created_at=version.created_at,
        )


class DealBreakerSave(BaseModel):
    text: NonBlank


class DealBreakerRead(BaseModel):
    id: int  # stable across versions of the set
    text: str


class DealBreakerSetVersionRead(BaseModel):
    id: int
    number: int
    created_at: datetime
    deal_breakers: list[DealBreakerRead]

    @classmethod
    def of(cls, version: DealBreakerSetVersion) -> "DealBreakerSetVersionRead":
        return cls(
            id=version.id,
            number=version.number,
            created_at=version.created_at,
            deal_breakers=[
                DealBreakerRead(id=item.deal_breaker_id, text=item.text) for item in version.items
            ],
        )


def version_number(version: DocumentVersion | DealBreakerSetVersion | None) -> int | None:
    """A version's number as the user sees it; null when the input was missing."""
    return None if version is None else version.number
