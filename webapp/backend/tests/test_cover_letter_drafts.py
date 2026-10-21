"""Cover Letter drafts after the first: hand edits, revisions in words, restore, delete,
the edited-posting badge and locking with the Application's state."""

from typing import Any

import httpx
from test_applications import edit_posting_text, move, started_application
from test_cover_letters import RunTasks, a_letter, cover_letter, generate, sent
from test_evaluations import write_career_profile

from job_scout.config import Settings
from job_scout.llm.fake import FakeLlm


async def save_draft(client: httpx.AsyncClient, application_id: int, text: str) -> httpx.Response:
    return await client.post(
        f"/api/applications/{application_id}/cover-letter/drafts", json={"text": text}
    )


async def revise(
    client: httpx.AsyncClient,
    application_id: int,
    instruction: str,
    *,
    evaluation_case: str = "current",
) -> httpx.Response:
    return await client.post(
        f"/api/applications/{application_id}/cover-letter/revisions",
        json={"evaluation_case": evaluation_case, "instruction": instruction},
    )


async def generated_application(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks, letter: str
) -> dict[str, Any]:
    """An Application Preparing whose Cover Letter is one generated draft, `letter`."""
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks)
    fake_llm.cover_letter.respond_with(a_letter(letter=letter))
    await generate(client, application["id"], instruction="Lead with Kafka.")
    await run_queued_tasks()
    return application


async def test_a_hand_edit_is_saved_as_the_latest_draft_keeping_the_earlier_one(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    application = await generated_application(client, fake_llm, run_queued_tasks, "Generated.")
    generated = (await cover_letter(client, application["id"]))["draft"]

    saved = await save_draft(client, application["id"], "Generated, then edited by me.")

    assert saved.status_code == 201
    letter = await cover_letter(client, application["id"])
    draft = letter["draft"]
    assert draft["text"] == "Generated, then edited by me."
    assert draft["origin"] == "edited_by_hand"
    assert draft["instruction"] is None
    assert draft["model"] is None
    # Still what the posting asks for that the profile lacks
    assert draft["unsupported_requirements"] == ["Five years of Scala"]
    assert [d["id"] for d in letter["drafts"]] == [draft["id"], generated["id"]]
    assert letter["drafts"][1] == generated


async def test_a_revision_in_words_sends_the_hand_edited_text_with_the_instruction(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    application = await generated_application(client, fake_llm, run_queued_tasks, "Generated.")
    await save_draft(client, application["id"], "HAND EDITED: my own opening.")
    fake_llm.cover_letter.respond_with(
        a_letter(letter="Revised.", unsupported_requirements=["A driving licence"])
    )

    requested = await revise(client, application["id"], "Shorter, and lead with Kafka.")
    assert requested.status_code == 201
    assert requested.json()["generation"]["status"] == "queued"
    await run_queued_tasks()

    user_inputs, request = fake_llm.cover_letter.calls[-1].blocks
    assert "HAND EDITED: my own opening." in request
    assert "Generated." not in request
    assert "Shorter, and lead with Kafka." in request
    # The same inputs as generating: the profile, the posting and the flags
    assert "Ten years of Python." in user_inputs
    assert "Python pipelines are the core of their experience." in sent(fake_llm)
    letter = await cover_letter(client, application["id"])
    draft = letter["draft"]
    assert draft["text"] == "Revised."
    assert draft["origin"] == "revised_in_words"
    assert draft["instruction"] == "Shorter, and lead with Kafka."
    assert draft["unsupported_requirements"] == ["A driving licence"]
    assert draft["model"] == "claude-opus-5-5"
    assert letter["generation"]["draft_id"] == draft["id"]
    assert [d["origin"] for d in letter["drafts"]] == [
        "revised_in_words",
        "edited_by_hand",
        "generated",
    ]


async def test_a_revision_needs_a_draft_and_a_confirmed_evaluation_case(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks)

    nothing_to_revise = await revise(client, application["id"], "Shorter.")
    assert nothing_to_revise.status_code == 409
    assert "draft" in nothing_to_revise.json()["detail"]
    await save_draft(client, application["id"], "My own letter.")
    unconfirmed = await revise(client, application["id"], "Shorter.", evaluation_case="missing")
    assert unconfirmed.status_code == 409
    assert (await revise(client, application["id"], "  ")).status_code == 422
    assert (await cover_letter(client, application["id"]))["generation"] is None


async def test_regenerating_writes_from_scratch_without_the_latest_draft(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    application = await generated_application(client, fake_llm, run_queued_tasks, "Generated.")
    await save_draft(client, application["id"], "HAND EDITED: my own opening.")
    fake_llm.cover_letter.respond_with(a_letter(letter="Regenerated."))

    await generate(client, application["id"])
    await run_queued_tasks()

    assert "HAND EDITED" not in sent(fake_llm)
    assert "draft_to_revise" not in sent(fake_llm)
    letter = await cover_letter(client, application["id"])
    assert letter["draft"]["text"] == "Regenerated."
    assert letter["draft"]["origin"] == "generated"
    assert letter["generation"]["revised_draft_id"] is None
    assert len(letter["drafts"]) == 3


async def restore(client: httpx.AsyncClient, application_id: int, draft_id: int) -> httpx.Response:
    return await client.post(
        f"/api/applications/{application_id}/cover-letter/drafts/{draft_id}/restore"
    )


async def test_restoring_an_earlier_draft_makes_a_new_latest_draft_with_its_text_and_record(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    application = await generated_application(client, fake_llm, run_queued_tasks, "Generated.")
    generated = (await cover_letter(client, application["id"]))["draft"]
    await save_draft(client, application["id"], "A hand edit I regret.")

    restored = await restore(client, application["id"], generated["id"])

    assert restored.status_code == 201
    letter = await cover_letter(client, application["id"])
    draft = letter["draft"]
    assert draft["text"] == "Generated."
    assert draft["restored_from_draft_id"] == generated["id"]
    unchanged = ["id", "created_at", "restored_from_draft_id"]
    assert {k: v for k, v in draft.items() if k not in unchanged} == {
        k: v for k, v in generated.items() if k not in unchanged
    }
    assert [d["text"] for d in letter["drafts"]] == [
        "Generated.",
        "A hand edit I regret.",
        "Generated.",
    ]


async def test_only_a_live_draft_of_the_application_can_be_restored(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    application = await generated_application(client, fake_llm, run_queued_tasks, "Mine.")
    draft_id = (await cover_letter(client, application["id"]))["draft"]["id"]
    other = await started_application(client, fake_llm, run_queued_tasks, "Other")

    assert (await restore(client, other["id"], draft_id)).status_code == 404
    assert (await restore(client, application["id"], 999)).status_code == 404


async def delete_draft(
    client: httpx.AsyncClient, application_id: int, draft_id: int
) -> httpx.Response:
    return await client.delete(f"/api/applications/{application_id}/cover-letter/drafts/{draft_id}")


async def test_a_deleted_draft_is_hidden_and_the_one_before_it_is_the_letter_again(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    application = await generated_application(client, fake_llm, run_queued_tasks, "Generated.")
    generated = (await cover_letter(client, application["id"]))["draft"]
    junk = (await save_draft(client, application["id"], "Junk.")).json()["draft"]

    deleted = await delete_draft(client, application["id"], junk["id"])

    assert deleted.status_code == 200
    letter = await cover_letter(client, application["id"])
    assert letter["draft"] == generated
    assert letter["drafts"] == [generated]
    assert (await delete_draft(client, application["id"], junk["id"])).status_code == 404
    assert (await restore(client, application["id"], junk["id"])).status_code == 404


async def test_the_letter_shows_when_the_posting_was_edited_since_its_latest_draft(
    client: httpx.AsyncClient,
    settings: Settings,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
) -> None:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks)
    assert (await cover_letter(client, application["id"]))["posting_edited_since_draft"] is None
    await generate(client, application["id"])
    await run_queued_tasks()
    generated = (await cover_letter(client, application["id"]))["draft"]
    assert (await cover_letter(client, application["id"]))["posting_edited_since_draft"] is False

    await edit_posting_text(
        settings, application["job_posting_id"], title="Staff Role", description="Lead the team."
    )

    assert (await cover_letter(client, application["id"]))["posting_edited_since_draft"] is True
    # A hand edit is as old as the text it edits
    await save_draft(client, application["id"], "A typo fixed.")
    assert (await cover_letter(client, application["id"]))["posting_edited_since_draft"] is True
    # A draft the LLM writes from the posting as it is now is up to date again
    assert (
        await generate(client, application["id"], evaluation_case="outdated")
    ).status_code == 201
    await run_queued_tasks()
    assert (await cover_letter(client, application["id"]))["posting_edited_since_draft"] is False
    # A restored draft is as old as the text it restores
    await restore(client, application["id"], generated["id"])
    assert (await cover_letter(client, application["id"]))["posting_edited_since_draft"] is True


async def test_every_action_is_refused_outside_preparing_and_moving_back_unlocks_them(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    application = await generated_application(client, fake_llm, run_queued_tasks, "Generated.")
    application_id = application["id"]
    before = await cover_letter(client, application_id)
    draft_id = before["draft"]["id"]

    for state in ["applied", "screen_call", "withdrawn"]:
        await move(client, application_id, state)
        for refused in [
            await save_draft(client, application_id, "A change."),
            await revise(client, application_id, "Shorter."),
            await generate(client, application_id),
            await restore(client, application_id, draft_id),
            await delete_draft(client, application_id, draft_id),
        ]:
            assert refused.status_code == 409
            assert "locked" in refused.json()["detail"]
        letter = await cover_letter(client, application_id)
        assert letter["editable"] is False
        assert letter["drafts"] == before["drafts"]
        assert letter["generation"] == before["generation"]

    await move(client, application_id, "preparing")

    assert (await cover_letter(client, application_id))["editable"] is True
    assert (await save_draft(client, application_id, "A change.")).status_code == 201
    assert (await restore(client, application_id, draft_id)).status_code == 201
    assert (await delete_draft(client, application_id, draft_id)).status_code == 200
    assert (await revise(client, application_id, "Shorter.")).status_code == 201
    await run_queued_tasks()
    assert (await cover_letter(client, application_id))["draft"]["origin"] == "revised_in_words"


async def test_moving_to_applied_with_no_draft_records_that_no_letter_was_sent(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks)
    assert (await cover_letter(client, application["id"]))["sent"] is None

    moved = await move(client, application["id"], "applied")

    assert moved.status_code == 200
    sent_letter = (await cover_letter(client, application["id"]))["sent"]
    assert sent_letter["draft"] is None
    assert sent_letter["applied_at"] == moved.json()["state_changed_at"]


async def test_each_move_to_applied_locks_the_then_latest_draft_as_the_sent_letter(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    application = await generated_application(client, fake_llm, run_queued_tasks, "Generated.")
    application_id = application["id"]
    await save_draft(client, application_id, "First sent.")

    await move(client, application_id, "applied")
    first = (await cover_letter(client, application_id))["sent"]
    assert first["draft"]["text"] == "First sent."
    # Moving on keeps the letter that was sent
    await move(client, application_id, "screen_call")
    assert (await cover_letter(client, application_id))["sent"] == first

    await move(client, application_id, "preparing")
    second = (await save_draft(client, application_id, "Sent again.")).json()["draft"]
    await move(client, application_id, "applied")

    letter = await cover_letter(client, application_id)
    assert letter["sent"]["draft"] == second
    assert letter["sent"]["applied_at"] > first["applied_at"]
    # Drafts are kept after locking
    assert [d["text"] for d in letter["drafts"]] == ["Sent again.", "First sent.", "Generated."]


async def test_a_deleted_draft_is_kept_as_the_letter_that_was_sent(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    application = await generated_application(client, fake_llm, run_queued_tasks, "Generated.")
    application_id = application["id"]
    sent_draft = (await cover_letter(client, application_id))["draft"]
    await move(client, application_id, "applied")
    await move(client, application_id, "preparing")

    await delete_draft(client, application_id, sent_draft["id"])

    letter = await cover_letter(client, application_id)
    assert letter["drafts"] == []
    assert letter["sent"]["draft"] == sent_draft
