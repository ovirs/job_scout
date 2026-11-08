"""The regeneration comparison: a quality aid the user starts by hand. For a handful of
Applications whose Cover Letter was sent, the LLM writes the letter again under another
prompt or model, to be read beside the letter sent. Nothing it writes is stored.

Each letter is written from scratch from what the last LLM draft before the letter sent
was written from: the same Career Profile and Writing Guide versions, the same
Evaluation's flags, and the same instruction when that draft was generated (a revision
in words asked for changes to a text the new letter does not have). The posting is the
Application's copy, as it was when first Applied. Only the prompt and the model change,
so differences come from them.

Deleted Applications and deleted drafts are left out, as everywhere: a letter sent with
no live LLM draft before it has nothing to be written again from.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from job_scout.applications.models import Application
from job_scout.cover_letters import domain as cover_letters
from job_scout.cover_letters import generation
from job_scout.cover_letters.generation import Inputs
from job_scout.cover_letters.models import CoverLetterDraft
from job_scout.cover_letters.prompt import CoverLetterResult
from job_scout.evaluations.models import Evaluation
from job_scout.llm.interface import Llm, Outcome
from job_scout.posting_text import PostingText
from job_scout.prompts import Prompt


class NotComparable(Exception):
    """Some Applications chosen have no letter to compare with; `reasons` says why, by
    Application id."""

    def __init__(self, reasons: dict[int, str]) -> None:
        super().__init__(reasons)
        self.reasons = reasons


@dataclass(frozen=True)
class Comparison:
    """One Application to write the letter again for: the letter sent, and what the last
    LLM draft before it was written from."""

    application: Application
    sent: CoverLetterDraft
    inputs: Inputs

    async def write_again(
        self, llm: Llm, *, model: str | None, instructions: Prompt | None
    ) -> Outcome[CoverLetterResult]:
        """The letter written again, with `model` and `instructions` when given, else the
        step's own; checked as a generation's answer is."""
        outcome = await llm.write_cover_letter(
            self.inputs.prompt(), model=model, instructions=instructions
        )
        return generation.check(outcome)


async def comparisons(
    session: AsyncSession, *, owner_id: uuid.UUID, application_ids: list[int]
) -> list[Comparison]:
    """What to write again for each Application, in the order given. Raises
    `NotComparable`, naming every Application that is unknown or deleted, has no letter
    sent, or had no live LLM draft before the letter sent."""
    found: list[Comparison] = []
    reasons: dict[int, str] = {}
    for application_id in application_ids:
        try:
            letter = await cover_letters.read(
                session, owner_id=owner_id, application_id=application_id
            )
        except cover_letters.NoSuchApplication:
            reasons[application_id] = "No such Application"
            continue
        sent = letter.sent
        if sent is None or sent.draft is None:
            reasons[application_id] = "No Cover Letter was sent with it"
        elif sent.llm_draft is None:
            reasons[application_id] = (
                "The LLM wrote none of the live drafts before the letter sent,"
                " so there is nothing to write it again from"
            )
        else:
            inputs = await _inputs(session, letter.application, sent.llm_draft)
            found.append(Comparison(letter.application, sent.draft, inputs))
    if reasons:
        raise NotComparable(reasons)
    return found


async def _inputs(
    session: AsyncSession, application: Application, llm_draft: CoverLetterDraft
) -> Inputs:
    """What `llm_draft` was written from, with the posting as the Application copied it."""
    assert application.copy_title is not None  # a letter was sent, so the posting copied
    assert application.copy_company is not None and application.copy_description is not None
    flags = None
    if llm_draft.evaluation_id is not None:
        flags = generation.flags_of(await session.get_one(Evaluation, llm_draft.evaluation_id))
    return Inputs(
        career_profile=llm_draft.career_profile_version,
        writing_guide=llm_draft.writing_guide_version,
        posting=PostingText(
            title=application.copy_title,
            company=application.copy_company,
            location_text=application.copy_location_text,
            description=application.copy_description,
        ),
        content_hash=llm_draft.content_hash,
        flags=flags,
        evaluation_case=llm_draft.evaluation_case or "missing",
        revised_text=None,
        instruction=llm_draft.instruction if llm_draft.origin == "generated" else None,
    )
