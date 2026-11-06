from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import APIRouter, HTTPException

from job_scout.cover_letters import domain as cover_letters
from job_scout.cover_letters.schemas import (
    CoverLetterDraftSave,
    CoverLetterGenerate,
    CoverLetterRead,
    CoverLetterRevise,
)
from job_scout.routing import Owner, Session, TaskQueue

router = APIRouter(prefix="/api")


@router.get("/applications/{application_id}/cover-letter")
async def get_cover_letter(application_id: int, session: Session, owner: Owner) -> CoverLetterRead:
    """The Application's Cover Letter, its latest generation request, and whether the
    posting's Evaluation is current, outdated or missing for the next one."""
    with _refusals():
        letter = await cover_letters.read(session, owner_id=owner, application_id=application_id)
    return CoverLetterRead.of(letter)


@router.post("/applications/{application_id}/cover-letter/generations", status_code=201)
async def generate_cover_letter(
    application_id: int,
    body: CoverLetterGenerate,
    session: Session,
    task_queue: TaskQueue,
    owner: Owner,
) -> CoverLetterRead:
    """Queue a new draft written by the LLM from the posting, the Career Profile, the
    Writing Guide, the Evaluation's flags and the instruction; poll the Cover Letter for
    it. Also the retry of a failed one. Refused unless the Application is Preparing, while
    there is no Career Profile, when `evaluation_case` is not the Evaluation's case now
    (the user must confirm a missing or outdated one), and while another request is under
    way, unless that one is stuck."""
    with _refusals():
        letter = await cover_letters.generate(
            session,
            task_queue,
            owner_id=owner,
            application_id=application_id,
            evaluation_case=body.evaluation_case,
            instruction=body.instruction,
        )
    return CoverLetterRead.of(letter)


@router.post("/applications/{application_id}/cover-letter/revisions", status_code=201)
async def revise_cover_letter(
    application_id: int,
    body: CoverLetterRevise,
    session: Session,
    task_queue: TaskQueue,
    owner: Owner,
) -> CoverLetterRead:
    """Queue a revision in words of the latest draft, hand edits included: the LLM gets its
    text and the instruction with the same inputs as generating, and its answer is a new
    draft. Refused as generating is, and while there is no draft to revise."""
    with _refusals():
        letter = await cover_letters.revise(
            session,
            task_queue,
            owner_id=owner,
            application_id=application_id,
            evaluation_case=body.evaluation_case,
            instruction=body.instruction,
        )
    return CoverLetterRead.of(letter)


@router.post("/applications/{application_id}/cover-letter/drafts", status_code=201)
async def save_cover_letter_draft(
    application_id: int, body: CoverLetterDraftSave, session: Session, owner: Owner
) -> CoverLetterRead:
    """Save the user's hand edit as the new latest draft; the earlier drafts are kept.
    Refused unless the Application is Preparing."""
    with _refusals():
        letter = await cover_letters.save(
            session, owner_id=owner, application_id=application_id, text=body.text
        )
    return CoverLetterRead.of(letter)


@router.post(
    "/applications/{application_id}/cover-letter/drafts/{draft_id}/restore", status_code=201
)
async def restore_cover_letter_draft(
    application_id: int, draft_id: int, session: Session, owner: Owner
) -> CoverLetterRead:
    """Make an earlier draft the letter again: a new latest draft copies its text and its
    record. Refused unless the Application is Preparing."""
    with _refusals():
        letter = await cover_letters.restore(
            session, owner_id=owner, application_id=application_id, draft_id=draft_id
        )
    return CoverLetterRead.of(letter)


@router.delete("/applications/{application_id}/cover-letter/drafts/{draft_id}")
async def delete_cover_letter_draft(
    application_id: int, draft_id: int, session: Session, owner: Owner
) -> CoverLetterRead:
    """Delete a draft: it is hidden but kept, and the latest draft left is the letter.
    Refused unless the Application is Preparing."""
    with _refusals():
        letter = await cover_letters.delete(
            session, owner_id=owner, application_id=application_id, draft_id=draft_id
        )
    return CoverLetterRead.of(letter)


@contextmanager
def _refusals() -> Iterator[None]:
    """Map the Cover Letter package's errors to HTTP."""
    try:
        yield
    except cover_letters.NoSuchApplication:
        raise HTTPException(status_code=404, detail="No such Application") from None
    except cover_letters.NoSuchDraft:
        raise HTTPException(status_code=404, detail="Cover Letter draft not found") from None
    except cover_letters.Refused as refusal:
        raise HTTPException(status_code=409, detail=str(refusal)) from None
