import uuid

import procrastinate
from fastapi import APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from job_scout import queue
from job_scout.applications.models import Application
from job_scout.applications.routes import application_or_404
from job_scout.cover_letters import domain as cover_letters
from job_scout.cover_letters.models import CoverLetterDraft, EvaluationCase
from job_scout.cover_letters.schemas import (
    CoverLetterDraftRead,
    CoverLetterDraftSave,
    CoverLetterEvaluationRead,
    CoverLetterGenerate,
    CoverLetterGenerationRead,
    CoverLetterRead,
    CoverLetterRevise,
    SentCoverLetterRead,
)
from job_scout.routing import Owner, Session, TaskQueue
from job_scout.user_inputs import domain as user_inputs

router = APIRouter(prefix="/api")


@router.get("/applications/{application_id}/cover-letter")
async def get_cover_letter(application_id: int, session: Session, owner: Owner) -> CoverLetterRead:
    """The Application's Cover Letter, its latest generation request, and whether the
    posting's Evaluation is current, outdated or missing for the next one."""
    application = await application_or_404(session, owner, application_id)
    return await _cover_letter_read(session, application)


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
    there is no Career Profile, and when `evaluation_case` is not the Evaluation's case
    now (the user must confirm a missing or outdated one)."""
    application = await _editable_application(session, owner, application_id)
    await _queue_generation(
        session, task_queue, application, body.evaluation_case, body.instruction
    )
    return await _cover_letter_read(session, application)


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
    application = await _editable_application(session, owner, application_id)
    latest = await cover_letters.latest_draft(session, application)
    if latest is None:
        raise HTTPException(
            status_code=409, detail="There is no draft to revise: generate or write one first"
        )
    await _queue_generation(
        session, task_queue, application, body.evaluation_case, body.instruction, latest
    )
    return await _cover_letter_read(session, application)


async def _queue_generation(
    session: AsyncSession,
    task_queue: procrastinate.App,
    application: Application,
    evaluation_case: EvaluationCase,
    instruction: str | None,
    revised: CoverLetterDraft | None = None,
) -> None:
    """Queue a generation, refused while there is no Career Profile and when
    `evaluation_case` is not the Evaluation's case now."""
    profile = await user_inputs.current_document(
        session, owner_id=application.owner_id, kind="career-profile"
    )
    missing = cover_letters.missing_input(profile)
    if missing is not None:
        raise HTTPException(status_code=409, detail=missing)
    source = await cover_letters.flags_source(session, application)
    if evaluation_case != source.case:
        raise HTTPException(
            status_code=409,
            detail=f"The posting's Evaluation is {source.case}, not {evaluation_case}: "
            "confirm that case to generate",
        )
    generation = cover_letters.queued(application, source, instruction, revised)
    session.add(generation)
    await session.commit()
    await queue.enqueue_generate_cover_letter(task_queue, generation.id)


@router.post("/applications/{application_id}/cover-letter/drafts", status_code=201)
async def save_cover_letter_draft(
    application_id: int, body: CoverLetterDraftSave, session: Session, owner: Owner
) -> CoverLetterRead:
    """Save the user's hand edit as the new latest draft; the earlier drafts are kept.
    Refused unless the Application is Preparing."""
    application = await _editable_application(session, owner, application_id)
    latest = await cover_letters.latest_draft(session, application)
    session.add(cover_letters.edited_by_hand(application, latest, body.text))
    await session.commit()
    return await _cover_letter_read(session, application)


@router.post(
    "/applications/{application_id}/cover-letter/drafts/{draft_id}/restore", status_code=201
)
async def restore_cover_letter_draft(
    application_id: int, draft_id: int, session: Session, owner: Owner
) -> CoverLetterRead:
    """Make an earlier draft the letter again: a new latest draft copies its text and its
    record. Refused unless the Application is Preparing."""
    application = await _editable_application(session, owner, application_id)
    session.add(cover_letters.restored(await _draft(session, application, draft_id)))
    await session.commit()
    return await _cover_letter_read(session, application)


@router.delete("/applications/{application_id}/cover-letter/drafts/{draft_id}")
async def delete_cover_letter_draft(
    application_id: int, draft_id: int, session: Session, owner: Owner
) -> CoverLetterRead:
    """Delete a draft: it is hidden but kept, and the latest draft left is the letter.
    Refused unless the Application is Preparing."""
    application = await _editable_application(session, owner, application_id)
    cover_letters.delete_draft(await _draft(session, application, draft_id))
    await session.commit()
    return await _cover_letter_read(session, application)


async def _draft(
    session: AsyncSession, application: Application, draft_id: int
) -> CoverLetterDraft:
    found = await cover_letters.draft(session, application, draft_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Cover Letter draft not found")
    return found


async def _editable_application(
    session: AsyncSession, owner: uuid.UUID, application_id: int
) -> Application:
    """The Application, if its Cover Letter can be changed now: only while Preparing."""
    application = await application_or_404(session, owner, application_id)
    if not cover_letters.editable(application):
        raise HTTPException(
            status_code=409,
            detail="The Cover Letter is locked: it changes only while the Application is Preparing",
        )
    return application


async def _cover_letter_read(session: AsyncSession, application: Application) -> CoverLetterRead:
    drafts = await cover_letters.drafts(session, application)
    draft = drafts[0] if drafts else None
    applied = cover_letters.latest_move_to_applied(application)
    generation = await cover_letters.latest_generation(session, application)
    source = await cover_letters.flags_source(session, application)
    return CoverLetterRead(
        application_id=application.id,
        editable=cover_letters.editable(application),
        draft=None if draft is None else CoverLetterDraftRead.of(draft),
        drafts=[CoverLetterDraftRead.of(d) for d in drafts],
        posting_edited_since_draft=cover_letters.posting_edited_since(draft, application),
        sent=None
        if applied is None
        else SentCoverLetterRead(
            applied_at=applied.changed_at,
            draft=None
            if applied.sent_draft is None
            else CoverLetterDraftRead.of(applied.sent_draft),
        ),
        generation=None if generation is None else CoverLetterGenerationRead.of(generation),
        evaluation=CoverLetterEvaluationRead(
            case=source.case,
            evaluation_id=None if source.evaluation is None else source.evaluation.id,
        ),
    )
