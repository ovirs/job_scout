"""The Cover Letter rules, at the package's interface: the lock, the inputs a generation
needs, the Evaluation case the user confirms, and what a revision revises."""

from collections.abc import AsyncIterator, Callable
from typing import Any, get_args

import httpx
import pytest
from test_applications import edit_posting_text, move, start, started_application
from test_cover_letters import RunTasks
from test_evaluations import write_career_profile
from test_triage import add_posting

from job_scout.config import Settings
from job_scout.cover_letters import domain as cover_letters
from job_scout.cover_letters.models import CoverLetterGeneration, EvaluationCase
from job_scout.llm import Failure
from job_scout.llm.fake import FakeLlm, FakeModelLister
from job_scout.owners import LOCAL_USER_ID
from job_scout.runtime import Runtime, open_runtime


@pytest.fixture
async def runtime(settings: Settings) -> AsyncIterator[Runtime]:
    async with open_runtime(settings) as runtime:
        yield runtime


@pytest.fixture
async def application(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> dict[str, Any]:
    """An Application Preparing, its posting evaluated, with a Career Profile written."""
    await write_career_profile(client)
    return await started_application(client, fake_llm, run_queued_tasks)


async def read(runtime: Runtime, application_id: int) -> cover_letters.CoverLetter:
    async with runtime.sessions() as session:
        return await cover_letters.read(
            session, owner_id=LOCAL_USER_ID, application_id=application_id
        )


async def generate(
    runtime: Runtime,
    application_id: int,
    evaluation_case: EvaluationCase = "current",
    instruction: str | None = None,
) -> cover_letters.CoverLetter:
    async with runtime.sessions() as session:
        return await cover_letters.generate(
            session,
            runtime.task_queue,
            FakeModelLister(),
            owner_id=LOCAL_USER_ID,
            application_id=application_id,
            evaluation_case=evaluation_case,
            instruction=instruction,
            choice=None,
        )


async def revise(
    runtime: Runtime,
    application_id: int,
    instruction: str = "Shorter.",
    evaluation_case: EvaluationCase = "current",
) -> cover_letters.CoverLetter:
    async with runtime.sessions() as session:
        return await cover_letters.revise(
            session,
            runtime.task_queue,
            FakeModelLister(),
            owner_id=LOCAL_USER_ID,
            application_id=application_id,
            evaluation_case=evaluation_case,
            instruction=instruction,
            choice=None,
        )


async def save(runtime: Runtime, application_id: int, text: str) -> cover_letters.CoverLetter:
    async with runtime.sessions() as session:
        return await cover_letters.save(
            session, owner_id=LOCAL_USER_ID, application_id=application_id, text=text
        )


async def restore(
    runtime: Runtime, application_id: int, draft_id: int
) -> cover_letters.CoverLetter:
    async with runtime.sessions() as session:
        return await cover_letters.restore(
            session, owner_id=LOCAL_USER_ID, application_id=application_id, draft_id=draft_id
        )


async def delete(runtime: Runtime, application_id: int, draft_id: int) -> cover_letters.CoverLetter:
    async with runtime.sessions() as session:
        return await cover_letters.delete(
            session, owner_id=LOCAL_USER_ID, application_id=application_id, draft_id=draft_id
        )


def texts(letter: cover_letters.CoverLetter) -> list[str]:
    return [draft.text for draft in letter.drafts]


@pytest.mark.parametrize("state", ["applied", "screen_call", "withdrawn"])
async def test_every_change_is_refused_as_locked_outside_preparing(
    runtime: Runtime, client: httpx.AsyncClient, application: dict[str, Any], state: str
) -> None:
    application_id = application["id"]
    draft = (await save(runtime, application_id, "My letter.")).draft
    assert draft is not None
    await move(client, application_id, state)

    for change in [
        generate(runtime, application_id),
        revise(runtime, application_id),
        save(runtime, application_id, "A change."),
        restore(runtime, application_id, draft.id),
        delete(runtime, application_id, draft.id),
    ]:
        with pytest.raises(cover_letters.Locked):
            await change

    letter = await read(runtime, application_id)
    assert letter.editable is False
    assert texts(letter) == ["My letter."]
    assert letter.generation is None


async def test_moving_back_to_preparing_unlocks_the_letter(
    runtime: Runtime, client: httpx.AsyncClient, application: dict[str, Any]
) -> None:
    application_id = application["id"]
    await move(client, application_id, "applied")
    await move(client, application_id, "preparing")

    letter = await save(runtime, application_id, "My letter.")

    assert letter.editable is True
    assert texts(letter) == ["My letter."]


async def test_generating_and_revising_are_refused_while_there_is_no_career_profile(
    runtime: Runtime, client: httpx.AsyncClient, application: dict[str, Any]
) -> None:
    await save(runtime, application["id"], "My letter.")
    await write_career_profile(client, "  ")

    for request in [generate(runtime, application["id"]), revise(runtime, application["id"])]:
        with pytest.raises(cover_letters.MissingInput, match="Career Profile"):
            await request

    assert (await read(runtime, application["id"])).generation is None


async def test_only_the_evaluations_case_now_can_be_confirmed(
    runtime: Runtime,
    client: httpx.AsyncClient,
    settings: Settings,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    application: dict[str, Any],
) -> None:
    outdated = await started_application(client, fake_llm, run_queued_tasks, "Edited")
    await edit_posting_text(
        settings, outdated["job_posting_id"], title="Edited", description="Changed."
    )
    not_evaluated = await add_posting(
        client, fake_llm, run_queued_tasks, "Broken", result=Failure("error", "Overloaded")
    )
    missing = (await start(client, not_evaluated)).json()  # its Evaluation left queued

    cases: list[tuple[int, EvaluationCase]] = [
        (application["id"], "current"),
        (missing["id"], "missing"),
        (outdated["id"], "outdated"),
    ]
    for application_id, case in cases:
        letter = await read(runtime, application_id)
        assert letter.flags_source.case == case
        for wrong in get_args(EvaluationCase):
            if wrong != case:
                with pytest.raises(cover_letters.WrongEvaluationCase, match=f"{case}, not {wrong}"):
                    await generate(runtime, application_id, wrong)
        assert (await read(runtime, application_id)).generation is None
        queued = await generate(runtime, application_id, case)
        assert queued.generation is not None
        assert queued.generation.evaluation_case == case


async def test_revising_needs_a_draft_and_the_evaluations_case_now(
    runtime: Runtime, application: dict[str, Any]
) -> None:
    with pytest.raises(cover_letters.NothingToRevise):
        await revise(runtime, application["id"])
    await save(runtime, application["id"], "My letter.")
    with pytest.raises(cover_letters.WrongEvaluationCase):
        await revise(runtime, application["id"], evaluation_case="missing")
    assert (await read(runtime, application["id"])).generation is None

    letter = await revise(runtime, application["id"])

    assert letter.generation is not None
    assert letter.generation.revised_draft_id == letter.drafts[0].id


async def test_a_request_is_refused_while_another_is_under_way_unless_it_is_stuck(
    runtime: Runtime,
    application: dict[str, Any],
    make_stuck: Callable[[str, int], None],
) -> None:
    under_way = (await generate(runtime, application["id"])).generation
    assert under_way is not None
    await save(runtime, application["id"], "My letter.")

    for request in [generate(runtime, application["id"]), revise(runtime, application["id"])]:
        with pytest.raises(cover_letters.GenerationUnderWay):
            await request
    make_stuck("cover_letter_generations", under_way.id)

    replacing = (await generate(runtime, application["id"])).generation
    assert replacing is not None
    assert replacing.id != under_way.id
    async with runtime.sessions() as session:
        stuck = await session.get_one(CoverLetterGeneration, under_way.id)
    assert stuck.failure_kind == "stuck"


async def test_an_unknown_or_deleted_application_has_no_cover_letter(
    runtime: Runtime, client: httpx.AsyncClient, application: dict[str, Any]
) -> None:
    await client.delete(f"/api/applications/{application['id']}")

    for application_id in [999, application["id"]]:
        for request in [
            read(runtime, application_id),
            generate(runtime, application_id),
            save(runtime, application_id, "My letter."),
        ]:
            with pytest.raises(cover_letters.NoSuchApplication):
                await request


async def test_only_a_live_draft_of_the_application_can_be_restored_or_deleted(
    runtime: Runtime,
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    application: dict[str, Any],
) -> None:
    letter = await save(runtime, application["id"], "Mine.")
    mine = letter.drafts[0].id
    other = await started_application(client, fake_llm, run_queued_tasks, "Other")
    deleted = (await save(runtime, application["id"], "Deleted.")).drafts[0].id
    await delete(runtime, application["id"], deleted)

    for application_id, draft_id in [(other["id"], mine), (application["id"], 999)] + [
        (application["id"], deleted)
    ]:
        for change in [
            restore(runtime, application_id, draft_id),
            delete(runtime, application_id, draft_id),
        ]:
            with pytest.raises(cover_letters.NoSuchDraft):
                await change

    assert texts(await read(runtime, application["id"])) == ["Mine."]


async def test_the_letter_sent_is_the_latest_draft_on_each_move_to_applied(
    runtime: Runtime, client: httpx.AsyncClient, application: dict[str, Any]
) -> None:
    application_id = application["id"]
    await save(runtime, application_id, "Not sent.")
    await save(runtime, application_id, "First sent.")

    await move(client, application_id, "applied")
    first = (await read(runtime, application_id)).sent
    assert first is not None and first.draft is not None
    assert first.draft.text == "First sent."
    # Moving on keeps the letter that was sent
    await move(client, application_id, "screen_call")
    kept = (await read(runtime, application_id)).sent
    assert kept is not None and kept.draft is not None
    assert (kept.applied_at, kept.draft.id) == (first.applied_at, first.draft.id)

    await move(client, application_id, "preparing")
    await save(runtime, application_id, "Sent again.")
    await move(client, application_id, "applied")

    letter = await read(runtime, application_id)
    assert letter.sent is not None and letter.sent.draft is not None
    assert letter.sent.draft.text == "Sent again."
    assert letter.sent.applied_at > first.applied_at
    # Drafts are kept after the letter is sent
    assert texts(letter) == ["Sent again.", "First sent.", "Not sent."]


async def test_a_draft_deleted_before_the_move_is_not_sent_and_one_deleted_after_stays_sent(
    runtime: Runtime, client: httpx.AsyncClient, application: dict[str, Any]
) -> None:
    application_id = application["id"]
    await save(runtime, application_id, "Kept.")
    junk = (await save(runtime, application_id, "Junk.")).drafts[0]
    await delete(runtime, application_id, junk.id)
    await move(client, application_id, "applied")
    sent = (await read(runtime, application_id)).sent
    assert sent is not None and sent.draft is not None
    assert sent.draft.text == "Kept."

    await move(client, application_id, "preparing")
    await delete(runtime, application_id, sent.draft.id)

    letter = await read(runtime, application_id)
    assert letter.drafts == []
    assert letter.sent is not None and letter.sent.draft is not None
    assert letter.sent.draft.text == "Kept."
