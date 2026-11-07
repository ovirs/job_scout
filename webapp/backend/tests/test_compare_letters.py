"""The command that writes past letters again to compare, through its entry point."""

import io
from pathlib import Path
from typing import Any

import httpx
import pytest
from test_applications import delete, move, started_application
from test_cover_letter_drafts import generated_application, save_draft
from test_cover_letters import RunTasks, cover_letter

from job_scout import compare_letters
from job_scout.config import Settings
from job_scout.cover_letters.prompt import CoverLetterResult
from job_scout.llm import Failure
from job_scout.llm.fake import FakeLlm

NEW_PROMPT = "---\nversion: v3-candidate\n---\nWrite the letter, shorter.\n"


async def compare(settings: Settings, fake_llm: FakeLlm, *argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    status = await compare_letters.run(settings, list(argv), llm=fake_llm, out=out, err=err)
    return status, out.getvalue(), err.getvalue()


async def applied(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks, sent: str
) -> dict[str, Any]:
    application = await generated_application(client, fake_llm, run_queued_tasks, "Generated.")
    await save_draft(client, application["id"], sent)
    await move(client, application["id"], "applied")
    return application


async def test_each_letter_is_written_again_beside_the_letter_sent_and_nothing_is_saved(
    client: httpx.AsyncClient,
    settings: Settings,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    tmp_path: Path,
) -> None:
    first = await applied(client, fake_llm, run_queued_tasks, "SENT ONE")
    before = await cover_letter(client, first["id"])
    calls_before = len(fake_llm.cover_letter.calls)
    fake_llm.cover_letter.respond_with(
        CoverLetterResult(letter="REWRITTEN", unsupported_requirements=[])
    )
    prompt_file = tmp_path / "candidate.md"
    prompt_file.write_text(NEW_PROMPT)

    status, out, err = await compare(
        settings,
        fake_llm,
        "--application",
        str(first["id"]),
        "--prompt-file",
        str(prompt_file),
        "--model",
        "claude-sonnet-5-5",
    )

    assert (status, err) == (0, "")
    assert "SENT ONE" in out and "REWRITTEN" in out
    assert out.index("SENT ONE") < out.index("REWRITTEN")
    assert "model claude-sonnet-5-5, prompt v3-candidate" in out
    assert len(fake_llm.cover_letter.calls) == calls_before + 1
    # No draft was made, no generation recorded: the Cover Letter is as it was
    assert await cover_letter(client, first["id"]) == before


async def test_a_failed_call_is_shown_in_place_of_the_letter(
    client: httpx.AsyncClient, settings: Settings, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    application = await applied(client, fake_llm, run_queued_tasks, "SENT ONE")
    fake_llm.cover_letter.respond_with(Failure("refusal", "No."))

    status, out, _ = await compare(
        settings, fake_llm, "--application", str(application["id"]), "--model", "m"
    )

    assert status == 0
    assert "SENT ONE" in out and "The LLM call failed: No." in out


async def test_deleted_and_never_sent_applications_are_refused_before_any_call(
    client: httpx.AsyncClient, settings: Settings, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    sent = await applied(client, fake_llm, run_queued_tasks, "SENT ONE")
    preparing = await started_application(client, fake_llm, run_queued_tasks, title="Other")
    deleted = await started_application(client, fake_llm, run_queued_tasks, title="Gone")
    await delete(client, deleted["id"])
    calls_before = len(fake_llm.cover_letter.calls)

    for other, message in [(deleted, "No such Application"), (preparing, "no Cover Letter sent")]:
        status, out, err = await compare(
            settings,
            fake_llm,
            "--application",
            str(sent["id"]),
            "--application",
            str(other["id"]),
            "--model",
            "m",
        )
        assert (status, out) == (1, "")
        assert message in err

    assert len(fake_llm.cover_letter.calls) == calls_before


async def test_a_deleted_draft_is_not_the_letter_sent(
    client: httpx.AsyncClient, settings: Settings, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    application = await generated_application(client, fake_llm, run_queued_tasks, "Generated.")
    await save_draft(client, application["id"], "KEPT")
    junk = (await save_draft(client, application["id"], "JUNK")).json()["draft"]
    await client.delete(f"/api/applications/{application['id']}/cover-letter/drafts/{junk['id']}")
    await move(client, application["id"], "applied")

    status, out, _ = await compare(
        settings, fake_llm, "--application", str(application["id"]), "--model", "m"
    )

    assert status == 0
    assert "KEPT" in out and "JUNK" not in out


async def test_there_must_be_a_prompt_or_a_model_to_compare(
    settings: Settings, fake_llm: FakeLlm
) -> None:
    with pytest.raises(SystemExit) as refused:
        await compare(settings, fake_llm, "--application", "1")
    assert refused.value.code == 2
