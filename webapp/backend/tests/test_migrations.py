"""Data migrations keep what the user sees of the data already stored."""

import httpx
import psycopg
import pytest
from clipping_helpers import save_manual_entry
from test_applications import move
from test_cover_letter_drafts import delete_draft, generated_application, save_draft
from test_cover_letters import RunTasks, cover_letter

from job_scout import migrations
from job_scout.config import Settings
from job_scout.llm.fake import FakeLlm


async def an_application_sent_then_its_draft_deleted(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> int:
    """An Application moved to Applied twice, the first letter's draft deleted since."""
    application_id: int = (
        await generated_application(client, fake_llm, run_queued_tasks, "Generated.")
    )["id"]
    first = (await save_draft(client, application_id, "First sent.")).json()["draft"]
    await move(client, application_id, "applied")
    await move(client, application_id, "preparing")
    await delete_draft(client, application_id, first["id"])
    await save_draft(client, application_id, "Second sent.")
    await move(client, application_id, "applied")
    return application_id


def sent_draft_ids(settings: Settings) -> list[int | None]:
    """The draft each move to Applied recorded as sent, before 0014 dropped them."""
    with psycopg.connect(settings.database_url) as conn:
        rows = conn.execute(
            "SELECT sent_draft_id FROM application_state_changes"
            " WHERE state = 'applied' ORDER BY id"
        ).fetchall()
    return [sent_draft_id for (sent_draft_id,) in rows]


async def test_the_sent_cover_letter_is_unchanged_across_dropping_its_stored_pointer(
    client: httpx.AsyncClient, settings: Settings, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    application_id = await an_application_sent_then_its_draft_deleted(
        client, fake_llm, run_queued_tasks
    )
    before = await cover_letter(client, application_id)
    drafts = {d["text"]: d["id"] for d in before["drafts"]}
    assert before["sent"]["draft"]["text"] == "Second sent."

    migrations.downgrade(settings.database_url, "0013")
    first_sent = sent_draft_ids(settings)[0]
    assert sent_draft_ids(settings) == [first_sent, drafts["Second sent."]]
    assert first_sent not in drafts.values()  # deleted since it was sent
    migrations.upgrade(settings.database_url)

    assert await cover_letter(client, application_id) == before


async def test_dropping_the_pointer_is_refused_when_a_stored_sent_letter_differs(
    client: httpx.AsyncClient, settings: Settings, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    application_id = await an_application_sent_then_its_draft_deleted(
        client, fake_llm, run_queued_tasks
    )
    generated = (await cover_letter(client, application_id))["drafts"][-1]["id"]
    migrations.downgrade(settings.database_url, "0013")
    with psycopg.connect(settings.database_url) as conn:
        changed = conn.execute(
            "UPDATE application_state_changes SET sent_draft_id = %s"
            " WHERE id = (SELECT max(id) FROM application_state_changes) RETURNING id",
            [generated],
        ).fetchone()
    assert changed is not None

    with pytest.raises(RuntimeError, match=rf"\[{changed[0]}\]"):
        migrations.upgrade(settings.database_url)


def model_choices(settings: Settings, table: str) -> list[tuple[str | None, ...]]:
    """Each run's requested Provider, model and effort, and the Provider that answered."""
    with psycopg.connect(settings.database_url) as conn:
        rows = conn.execute(
            "SELECT requested_provider, requested_model, requested_effort, provider, model"
            f" FROM {table} ORDER BY id"
        ).fetchall()
    return [tuple(row) for row in rows]


async def test_runs_stored_before_model_choices_are_filled_in_as_anthropic_runs(
    client: httpx.AsyncClient, settings: Settings, run_queued_tasks: RunTasks
) -> None:
    # A Clipping read by the LLM, and an Evaluation that failed before calling it, as
    # there is no Career Profile
    await save_manual_entry(client, run_queued_tasks)
    await run_queued_tasks()
    migrations.downgrade(settings.database_url, "0016")

    migrations.upgrade(settings.database_url)

    opus = "claude-opus-5-5"
    assert model_choices(settings, "clippings") == [("anthropic", opus, None, "anthropic", opus)]
    assert model_choices(settings, "evaluations") == [(None, None, None, None, None)]


async def test_drafts_stored_before_their_provider_and_effort_take_their_generations(
    client: httpx.AsyncClient, settings: Settings, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    high = {"provider": "anthropic", "model": "claude-opus-5-5", "effort": "high"}
    await client.put("/api/settings/defaults", json={"cover_letter": high})
    application_id: int = (
        await generated_application(client, fake_llm, run_queued_tasks, "Generated.")
    )["id"]
    generated = (await cover_letter(client, application_id))["draft"]
    await save_draft(client, application_id, "By hand.")
    await client.post(
        f"/api/applications/{application_id}/cover-letter/drafts/{generated['id']}/restore"
    )
    before = await cover_letter(client, application_id)
    migrations.downgrade(settings.database_url, "0017")

    migrations.upgrade(settings.database_url)

    assert await cover_letter(client, application_id) == before
    assert [(d["provider"], d["effort"]) for d in before["drafts"]] == [
        ("anthropic", "high"),  # restored
        (None, None),  # by hand
        ("anthropic", "high"),
    ]
