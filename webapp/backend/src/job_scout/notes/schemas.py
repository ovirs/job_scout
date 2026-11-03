from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from job_scout.notes.models import Note


class NoteAdd(BaseModel):
    text: Annotated[str, Field(min_length=1, pattern=r"\S")]  # stored as given


class NoteRead(BaseModel):
    """A note, on a posting or on an Application: exactly one of the two ids is set."""

    id: int
    job_posting_id: int | None
    application_id: int | None
    text: str
    created_at: datetime

    @classmethod
    def of(cls, note: Note) -> "NoteRead":
        return cls(
            id=note.id,
            job_posting_id=note.job_posting_id,
            application_id=note.application_id,
            text=note.text,
            created_at=note.created_at,
        )
