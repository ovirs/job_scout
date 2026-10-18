"""Triage and the lists that follow from it.

A posting's Triage is the user's own call (Interested, Maybe, Ignored); untriaged is
the absence of one. The lists are views over the user's postings, decided by the
Triage, whether the posting is closed and its Evaluations.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_scout import applications, evaluations
from job_scout.evaluation import Recommendation
from job_scout.models import Application, Evaluation, JobPosting, Triage, TriageValue

ListName = Literal["inbox", "skip", "not-evaluated", "shortlist", "later", "ignored"]
Sort = Literal["score", "age"]


async def set_triage(session: AsyncSession, posting: JobPosting, value: TriageValue) -> Triage:
    """The user's Triage of the posting: the first creates it, later ones change its value.

    Any posting can be triaged, whatever its Evaluation. While the posting has a live
    Application its Triage is locked at Interested: the caller refuses the change.
    """
    triage = await session.scalar(select(Triage).where(Triage.job_posting_id == posting.id))
    now = datetime.now(UTC)
    if triage is None:
        triage = Triage(
            owner_id=posting.owner_id,
            job_posting_id=posting.id,
            value=value,
            origin="user",
            created_at=now,
            changed_at=now,
        )
        session.add(triage)
    else:
        triage.value = value
        triage.origin = "user"
        triage.changed_at = now
    return triage


@dataclass(frozen=True)
class Entry:
    """A posting as a list shows it."""

    posting: JobPosting
    triage: Triage | None
    latest_evaluation: Evaluation | None  # done or not
    current_evaluation: Evaluation | None  # the latest done one
    application: Application | None  # the live one


async def triages_by_posting(
    session: AsyncSession, *, owner_id: uuid.UUID, job_posting_ids: list[int]
) -> dict[int, Triage]:
    triages = await session.scalars(
        select(Triage).where(
            Triage.owner_id == owner_id, Triage.job_posting_id.in_(job_posting_ids)
        )
    )
    return {triage.job_posting_id: triage for triage in triages}


async def entries(
    session: AsyncSession, *, owner_id: uuid.UUID, postings: list[JobPosting]
) -> list[Entry]:
    ids = [posting.id for posting in postings]
    triages = await triages_by_posting(session, owner_id=owner_id, job_posting_ids=ids)
    latest = await evaluations.latest_by_posting(session, owner_id=owner_id, job_posting_ids=ids)
    current = await evaluations.current_by_posting(session, owner_id=owner_id, job_posting_ids=ids)
    live_applications = await applications.live_by_posting(
        session, owner_id=owner_id, job_posting_ids=ids
    )
    return [
        Entry(
            posting,
            triages.get(posting.id),
            latest.get(posting.id),
            current.get(posting.id),
            live_applications.get(posting.id),
        )
        for posting in postings
    ]


def routed(entry: Entry) -> Recommendation | None:
    """What the posting is routed by: the stored (gated) recommendation, except for a
    disqualified but recommended posting, which goes by the LLM's own."""
    run = entry.current_evaluation
    if run is None:
        return None
    if run.disqualified_but_recommended:
        return run.llm_recommendation
    return run.recommendation


def in_list(entry: Entry, name: ListName) -> bool:
    triage = entry.triage.value if entry.triage else None
    open_ = entry.posting.closed_at is None
    match name:
        case "inbox":
            return triage is None and open_ and routed(entry) in ("apply", "maybe")
        case "skip":
            return triage is None and open_ and routed(entry) == "skip"
        case "not-evaluated":
            return triage is None and open_ and entry.current_evaluation is None
        case "shortlist":
            return triage == "interested"
        case "later":
            return triage == "maybe" and open_
        case "ignored":
            return triage == "ignored" and open_


DEFAULT_SORT: dict[ListName, Sort] = {
    "inbox": "score",
    "skip": "score",
    "not-evaluated": "age",
    "shortlist": "age",
    "later": "age",
    "ignored": "age",
}


def listing(all_entries: list[Entry], name: ListName, sort: Sort | None) -> list[Entry]:
    """The entries on a list: by score, highest first and unscored last, or by age,
    newest first. Equal ones keep the newest first."""
    members = [entry for entry in all_entries if in_list(entry, name)]
    members.sort(key=lambda e: (e.posting.created_at, e.posting.id), reverse=True)
    if (sort or DEFAULT_SORT[name]) == "score":
        members.sort(key=_score_desc)
    return members


def _score_desc(entry: Entry) -> tuple[bool, int]:
    run = entry.current_evaluation
    score = None if run is None or run.result is None else run.result["score"]
    return (score is None, 0 if score is None else -score)
