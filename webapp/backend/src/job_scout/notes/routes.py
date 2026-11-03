from fastapi import APIRouter, HTTPException

from job_scout.applications.routes import application_or_404
from job_scout.job_postings.routes import job_posting_or_404
from job_scout.notes import domain as notes
from job_scout.notes.schemas import NoteAdd, NoteRead
from job_scout.routing import Owner, Session

router = APIRouter(prefix="/api")


@router.get("/job-postings/{job_posting_id}/notes")
async def list_job_posting_notes(
    job_posting_id: int, session: Session, owner: Owner
) -> list[NoteRead]:
    """The posting's notes, the first first."""
    posting = await job_posting_or_404(session, owner, job_posting_id)
    return [NoteRead.of(note) for note in await notes.of_posting(session, posting)]


@router.post("/job-postings/{job_posting_id}/notes", status_code=201)
async def add_job_posting_note(
    job_posting_id: int, body: NoteAdd, session: Session, owner: Owner
) -> NoteRead:
    posting = await job_posting_or_404(session, owner, job_posting_id)
    note = notes.on_posting(posting, body.text)
    session.add(note)
    await session.commit()
    return NoteRead.of(note)


@router.get("/applications/{application_id}/notes")
async def list_application_notes(
    application_id: int, session: Session, owner: Owner
) -> list[NoteRead]:
    """The Application's notes and its posting's, together, the first first; each says
    which of the two it is on."""
    application = await application_or_404(session, owner, application_id)
    return [NoteRead.of(note) for note in await notes.of_application(session, application)]


@router.post("/applications/{application_id}/notes", status_code=201)
async def add_application_note(
    application_id: int, body: NoteAdd, session: Session, owner: Owner
) -> NoteRead:
    application = await application_or_404(session, owner, application_id)
    note = notes.on_application(application, body.text)
    session.add(note)
    await session.commit()
    return NoteRead.of(note)


@router.delete("/notes/{note_id}", status_code=204)
async def delete_note(note_id: int, session: Session, owner: Owner) -> None:
    """Delete a note, on a posting or on an Application: it is hidden everywhere but kept."""
    note = await notes.note(session, owner_id=owner, note_id=note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="No such note")
    notes.delete(note)
    await session.commit()
