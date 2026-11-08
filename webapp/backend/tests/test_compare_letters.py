"""The regeneration comparison command, through its entry point: Cover Letters written
again for chosen Applications under another prompt or model, each printed beside the
letter sent, with nothing saved."""

from pathlib import Path
from typing import Any

import httpx
import pytest
from test_applications import edit_posting_text, move, started_application
from test_cover_letter_drafts import delete_draft, generated_application, save_draft
from test_cover_letters import RunTasks, a_letter, cover_letter
from test_evaluations import write_career_profile

from job_scout import compare_letters
from job_scout.config import Settings
from job_scout.llm import Failure
from job_scout.llm.fake import FakeLlm

CANDIDATE_PROMPT = "---\nversion: v3-candidate\n---\nWrite a candid cover letter.\n"


async def sent_application(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks, sent: str
) -> dict[str, Any]:
    """An Application moved to Applied with `sent`, a hand edit of a generated draft."""
    application = await generated_application(client, fake_llm, run_queued_tasks, "Generated.")
    await save_draft(client, application["id"], sent)
    await move(client, application["id"], "applied")
    return application


async def compare(
    settings: Settings, fake_llm: FakeLlm, capsys: pytest.CaptureFixture[str], *args: str
) -> tuple[int, str, str]:
    """Run the command; its exit code, what it printed, and what it printed as errors."""
    code = await compare_letters.run(["--width", "120", *args], settings=settings, llm=fake_llm)
    printed = capsys.readouterr()
    return code, printed.out, printed.err


async def test_each_letter_is_written_again_and_printed_beside_the_letter_sent(
    client: httpx.AsyncClient,
    settings: Settings,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    first = await sent_application(client, fake_llm, run_queued_tasks, "Sent to the first.")
    second = await sent_application(client, fake_llm, run_queued_tasks, "Sent to the second.")
    before = [await cover_letter(client, a["id"]) for a in (first, second)]
    prompt_file = tmp_path / "candidate.md"
    prompt_file.write_text(CANDIDATE_PROMPT)
    fake_llm.cover_letter.respond_with(
        a_letter(letter="Written again for the first."),
        a_letter(letter="Written again for the second."),
    )

    code, out, _ = await compare(
        settings,
        fake_llm,
        capsys,
        str(first["id"]),
        str(second["id"]),
        "--model",
        "claude-candidate",
        "--prompt",
        str(prompt_file),
    )

    assert code == 0
    lines = out.splitlines()
    for sent, again in [
        ("Sent to the first.", "Written again for the first."),
        ("Sent to the second.", "Written again for the second."),
    ]:
        assert any(sent in line and again in line for line in lines), out
    assert out.count("model claude-candidate, prompt v3-candidate") == 2
    # Nothing written again is saved as a draft
    assert [await cover_letter(client, a["id"]) for a in (first, second)] == before


async def test_a_letter_is_written_again_from_what_its_last_llm_draft_was_written_from(
    client: httpx.AsyncClient,
    settings: Settings,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    capsys: pytest.CaptureFixture[str],
) -> None:
    application = await sent_application(client, fake_llm, run_queued_tasks, "Sent.")
    # Inputs changed since the letter was sent
    await write_career_profile(client, "Twenty years of Rust.")
    await edit_posting_text(settings, application["job_posting_id"], title="Staff Role")

    code, _, _ = await compare(settings, fake_llm, capsys, str(application["id"]))

    assert code == 0
    user_inputs, request = fake_llm.cover_letter.calls[-1].blocks
    assert "Ten years of Python." in user_inputs
    assert "Twenty years of Rust." not in user_inputs
    assert "Title: Role" in request
    assert "Staff Role" not in request
    assert "Lead with Kafka." in request  # the instruction it was generated with
    assert "Python pipelines are the core of their experience." in request  # its flags


async def test_applications_with_no_letter_to_compare_are_refused_before_any_is_written(
    client: httpx.AsyncClient,
    settings: Settings,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    capsys: pytest.CaptureFixture[str],
) -> None:
    comparable = await sent_application(client, fake_llm, run_queued_tasks, "Sent.")
    deleted = await started_application(client, fake_llm, run_queued_tasks, "Deleted")
    await client.delete(f"/api/applications/{deleted['id']}")
    not_sent = await started_application(client, fake_llm, run_queued_tasks, "Not sent")
    await move(client, not_sent["id"], "applied")
    # Its only LLM draft was deleted before the letter was sent
    hand_written = await generated_application(client, fake_llm, run_queued_tasks, "LLM.")
    generated = (await cover_letter(client, hand_written["id"]))["draft"]
    await save_draft(client, hand_written["id"], "All my own.")
    await delete_draft(client, hand_written["id"], generated["id"])
    await move(client, hand_written["id"], "applied")
    calls_before = len(fake_llm.cover_letter.calls)

    code, out, err = await compare(
        settings,
        fake_llm,
        capsys,
        *(str(a["id"]) for a in (comparable, deleted, not_sent, hand_written)),
        "999",
    )

    assert code == 2
    assert out == ""
    assert len(fake_llm.cover_letter.calls) == calls_before
    refused = err.splitlines()
    assert [line.split(":")[0] for line in refused] == [
        f"Application {a['id']}" for a in (deleted, not_sent, hand_written)
    ] + ["Application 999"]
    assert "No such Application" in refused[0]
    assert "No Cover Letter was sent" in refused[1]
    assert "nothing to write it again from" in refused[2]


async def test_a_failed_call_is_shown_in_place_of_its_letter_and_the_others_are_written(
    client: httpx.AsyncClient,
    settings: Settings,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = await sent_application(client, fake_llm, run_queued_tasks, "Sent to the first.")
    second = await sent_application(client, fake_llm, run_queued_tasks, "Sent to the second.")
    fake_llm.cover_letter.respond_with(
        Failure("refusal", "The model declined to answer"),
        a_letter(letter="Written again for the second."),
    )

    code, out, _ = await compare(settings, fake_llm, capsys, str(first["id"]), str(second["id"]))

    assert code == 1
    lines = out.splitlines()
    assert any(
        "Sent to the first." in line and "Not written: The model declined to answer" in line
        for line in lines
    ), out
    assert any(
        "Sent to the second." in line and "Written again for the second." in line for line in lines
    ), out
