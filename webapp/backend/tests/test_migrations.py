"""Data migrations keep what the user sees of the data already stored."""

import httpx
import psycopg
import pytest
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
