"""Clippings: pasted text of a Job Posting, read by the LLM before the user confirms it.

Each operation enforces the status it needs and refuses with `WrongStatus` otherwise.
"""

import uuid
from dataclasses import dataclass

import procrastinate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_scout.clippings.extraction import ManualEntryExtraction
from job_scout.clippings.models import Clipping
from job_scout.clippings.tasks import EXTRACTION
from job_scout.evaluations import domain as evaluations
from job_scout.evaluations.models import Evaluation
from job_scout.evaluations.tasks import EVALUATION
from job_scout.job_postings import domain as job_postings
from job_scout.job_postings.extraction import WorkplaceType
from job_scout.job_postings.models import JobPosting
from job_scout.llm.interface import ModelChoice, ModelLister
from job_scout.llm_runs import domain as llm_runs


class NoSuchClipping(Exception):
    """The owner has no Clipping with this id."""


class WrongStatus(Exception):
    """The Clipping's status does not allow the operation; the message says which does."""


async def submit(
    session: AsyncSession,
    task_queue: procrastinate.App,
    lister: ModelLister,
    *,
    owner_id: uuid.UUID,
    pasted_text: str,
    url: str | None,
    choice: ModelChoice | None,
) -> Clipping:
    """Store the pasted text as a new Clipping and queue its extraction, with the model
    choice given or else the step's default. Raises `settings.NotUsable` or
    `settings.NoUsableChoice`, storing nothing, when that cannot be used."""
    clipping = Clipping(owner_id=owner_id, pasted_text=pasted_text, url=url, status="queued")
    session.add(clipping)
    await llm_runs.choose(session, lister, EXTRACTION, clipping, choice)
    await llm_runs.commit_and_enqueue(session, task_queue, lister, EXTRACTION, clipping)
    return clipping


async def clipping(
    session: AsyncSession, *, owner_id: uuid.UUID, clipping_id: int, for_update: bool = False
) -> Clipping:
    """The owner's clipping; `for_update` locks it until the transaction ends, so two
    requests cannot both change it. Raises `NoSuchClipping`."""
    query = select(Clipping).where(Clipping.id == clipping_id, Clipping.owner_id == owner_id)
    found = await session.scalar(query.with_for_update() if for_update else query)
    if found is None:
        raise NoSuchClipping
    return found


async def retry(
    session: AsyncSession,
    task_queue: procrastinate.App,
    lister: ModelLister,
    *,
    owner_id: uuid.UUID,
    clipping_id: int,
    choice: ModelChoice | None,
) -> Clipping:
    """Queue the extraction of a failed clipping, or of one stuck being read, again, in
    place: with the model choice given, or else the one it was read with. Raises
    `WrongStatus` for any other, and `settings.NotUsable` or `settings.NoUsableChoice`,
    changing nothing, when the choice cannot be used."""
    found = await clipping(session, owner_id=owner_id, clipping_id=clipping_id, for_update=True)
    try:
        llm_runs.requeue(found)
    except (llm_runs.RunUnderWay, llm_runs.NotRetryable):
        raise WrongStatus(
            "Only a failed Clipping, or one stuck being read, can be retried"
        ) from None
    await llm_runs.choose(session, lister, EXTRACTION, found, choice)
    await llm_runs.commit_and_enqueue(session, task_queue, lister, EXTRACTION, found)
    return found


@dataclass(frozen=True)
class Confirmed:
    """The Manual Entry a Clipping was confirmed as, and its first Evaluation, queued."""

    posting: JobPosting
    evaluation: Evaluation


async def confirm(
    session: AsyncSession,
    task_queue: procrastinate.App,
    lister: ModelLister,
    *,
    owner_id: uuid.UUID,
    clipping_id: int,
    title: str,
    company: str,
    location_text: str | None,
    workplace_type: WorkplaceType | None,
    description: str,
) -> Confirmed:
    """Save a done clipping as a Manual Entry and queue its first Evaluation. Raises
    `WrongStatus` for any other clipping.

    The Manual Entry has the envelope as the user corrected it, the extracted fields as
    extracted, and the pasted text kept whole. It is never merged. The workplace type is
    both envelope and extracted fact; the user's correction is stored as both, so the
    two never disagree.
    """
    found = await clipping(session, owner_id=owner_id, clipping_id=clipping_id, for_update=True)
    if found.status != "done":
        raise WrongStatus("Only a done Clipping can be confirmed")
    extracted_fields = extraction(found).extracted_fields()
    extracted_fields.workplace_type = workplace_type
    posting = job_postings.new_manual_entry(
        owner_id=found.owner_id,
        title=title,
        company=company,
        location_text=location_text,
        workplace_type=workplace_type,
        description=description,
        url=found.url,
        pasted_text=found.pasted_text,
        extracted_fields=extracted_fields,
    )
    found.status = "confirmed"
    found.job_posting = posting
    session.add(posting)
    await session.flush()  # assigns the posting's id
    run = evaluations.queued(posting)
    session.add(run)
    await llm_runs.commit_and_enqueue(session, task_queue, lister, EVALUATION, run)
    return Confirmed(posting, run)


async def abandon(session: AsyncSession, *, owner_id: uuid.UUID, clipping_id: int) -> Clipping:
    """Leave a done or failed clipping unconfirmed for good; it is kept, never deleted.
    Raises `WrongStatus` for any other."""
    found = await clipping(session, owner_id=owner_id, clipping_id=clipping_id, for_update=True)
    if found.status not in ("done", "failed"):
        raise WrongStatus("Only a done or failed Clipping can be abandoned")
    found.status = "abandoned"
    await session.commit()
    return found


def extraction(clipping: Clipping) -> ManualEntryExtraction:
    assert clipping.extraction is not None
    return ManualEntryExtraction.model_validate(clipping.extraction)
