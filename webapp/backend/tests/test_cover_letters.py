from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from test_applications import edit_posting_text, move, start, started_application
from test_evaluations import a_result, current_evaluation, write_career_profile
from test_triage import add_posting

from job_scout.config import Settings
from job_scout.cover_letters.prompt import CoverLetterResult
from job_scout.llm import Failure
from job_scout.llm.fake import FakeLlm

RunTasks = Callable[[], Awaitable[None]]

LETTER = "Dear Acme team,\n\nI have built Python pipelines for ten years.\n\nKind regards"


def a_letter(**changes: object) -> CoverLetterResult:
    fields: dict[str, object] = {
        "letter": LETTER,
        "unsupported_requirements": ["Five years of Scala"],
    }
    return CoverLetterResult.model_validate({**fields, **changes})


async def write_writing_guide(client: httpx.AsyncClient, text: str = "Short and warm.") -> int:
    saved = await client.post("/api/documents/writing-guide/versions", json={"text": text})
    version_id: int = saved.json()["id"]
    return version_id


async def cover_letter(client: httpx.AsyncClient, application_id: int) -> dict[str, Any]:
    found: dict[str, Any] = (
        await client.get(f"/api/applications/{application_id}/cover-letter")
    ).json()
    return found


async def generate(
    client: httpx.AsyncClient,
    application_id: int,
    *,
    evaluation_case: str = "current",
    instruction: str | None = None,
) -> httpx.Response:
    return await client.post(
        f"/api/applications/{application_id}/cover-letter/generations",
        json={"evaluation_case": evaluation_case, "instruction": instruction},
    )


async def test_generating_while_preparing_makes_the_first_draft_with_its_record(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    profile_version = await write_career_profile(client)
    guide_version = await write_writing_guide(client)
    application = await started_application(client, fake_llm, run_queued_tasks)
    before = await cover_letter(client, application["id"])
    assert before["draft"] is None
    assert before["generation"] is None
    fake_llm.cover_letter.respond_with(a_letter())

    requested = await generate(client, application["id"], instruction="Lead with Kafka.")
    assert requested.status_code == 201
    assert requested.json()["generation"]["status"] == "queued"
    await run_queued_tasks()

    letter = await cover_letter(client, application["id"])
    assert letter["generation"]["status"] == "done"
    assert letter["generation"]["failure"] is None
    draft = letter["draft"]
    assert draft["text"] == LETTER
    assert draft["origin"] == "generated"
    assert draft["instruction"] == "Lead with Kafka."
    assert draft["unsupported_requirements"] == ["Five years of Scala"]
    assert draft["model"] == "claude-opus-5-5"
    assert draft["prompt_version"] == "v2"
    assert draft["career_profile_version_id"] == profile_version
    assert draft["career_profile_version_number"] == 1
    assert draft["writing_guide_version_id"] == guide_version
    assert draft["writing_guide_version_number"] == 1
    assert draft["created_at"] is not None
    assert len(fake_llm.cover_letter.calls) == 1


async def write_preferences_and_deal_breakers(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/documents/preferences/versions",
        json={"text": "PRIVATE PREFERENCE: I would rather avoid fintech."},
    )
    await client.post("/api/deal-breakers", json={"text": "PRIVATE DEAL BREAKER: no on-call."})


def sent(fake_llm: FakeLlm) -> str:
    """Everything the last Cover Letter call sent, its blocks joined."""
    return "\n".join(fake_llm.cover_letter.calls[-1].blocks)


async def test_the_letter_is_written_from_the_posting_profile_guide_flags_and_instruction(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client, "CAREER PROFILE: ten years of Python.")
    await write_writing_guide(client, "WRITING GUIDE: short and warm.")
    posting_id = await add_posting(
        client,
        fake_llm,
        run_queued_tasks,
        "Data Engineer",
        result=a_result(
            red_flags=[{"point": "RED FLAG: no Spark.", "evidence": ["Spark experience"]}],
        ),
    )
    application = (await start(client, posting_id)).json()
    # Written after the Evaluation, and current when the letter is generated
    await write_preferences_and_deal_breakers(client)

    requested = await generate(
        client, application["id"], instruction="INSTRUCTION: write in French."
    )
    assert requested.status_code == 201
    await run_queued_tasks()

    user_inputs, request = fake_llm.cover_letter.calls[-1].blocks
    # The Career Profile and Writing Guide come first, so they can be cached
    assert "CAREER PROFILE: ten years of Python." in user_inputs
    assert "WRITING GUIDE: short and warm." in user_inputs
    assert "Data Engineer" in request
    assert "Acme" in request
    assert "We are building the data platform behind Acme's payments." in request
    assert "Python pipelines are the core of their experience." in request  # a green flag
    assert "RED FLAG: no Spark." in request
    assert "INSTRUCTION: write in French." in request
    assert "PRIVATE" not in sent(fake_llm)
    draft = (await cover_letter(client, application["id"]))["draft"]
    assert draft["evaluation_case"] == "current"
    assert (
        draft["evaluation_id"]
        == (await current_evaluation(client, application["job_posting_id"]))["id"]
    )


async def test_with_no_evaluation_the_case_is_reported_and_the_letter_has_no_flags(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    posting_id = await add_posting(
        client, fake_llm, run_queued_tasks, "Broken", result=Failure("error", "Overloaded")
    )
    application = (await start(client, posting_id)).json()

    letter = await cover_letter(client, application["id"])
    assert letter["evaluation"] == {"case": "missing", "evaluation_id": None}
    unconfirmed = await generate(client, application["id"], evaluation_case="current")
    assert unconfirmed.status_code == 409
    assert "missing" in unconfirmed.json()["detail"]
    confirmed = await generate(client, application["id"], evaluation_case="missing")
    assert confirmed.status_code == 201
    await run_queued_tasks()

    assert "evaluation_flags" not in sent(fake_llm)
    assert "Python pipelines are the core of their experience." not in sent(fake_llm)
    draft = (await cover_letter(client, application["id"]))["draft"]
    assert draft["evaluation_case"] == "missing"
    assert draft["evaluation_id"] is None
    assert len(fake_llm.cover_letter.calls) == 1


async def test_with_an_outdated_evaluation_the_case_is_reported_and_its_flags_are_used(
    client: httpx.AsyncClient,
    settings: Settings,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
) -> None:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks, "Data Engineer")
    evaluation_id = (await current_evaluation(client, application["job_posting_id"]))["id"]
    assert (await cover_letter(client, application["id"]))["evaluation"] == {
        "case": "current",
        "evaluation_id": evaluation_id,
    }
    await edit_posting_text(
        settings,
        application["job_posting_id"],
        title="Staff Data Engineer",
        description="Lead the data platform team.",
    )

    letter = await cover_letter(client, application["id"])
    assert letter["evaluation"] == {"case": "outdated", "evaluation_id": evaluation_id}
    assert (await generate(client, application["id"], evaluation_case="current")).status_code == 409
    confirmed = await generate(client, application["id"], evaluation_case="outdated")
    assert confirmed.status_code == 201
    await run_queued_tasks()

    # The flags as they are, with the posting as it is now
    assert "Python pipelines are the core of their experience." in sent(fake_llm)
    assert "Lead the data platform team." in sent(fake_llm)
    draft = (await cover_letter(client, application["id"]))["draft"]
    assert draft["evaluation_case"] == "outdated"
    assert draft["evaluation_id"] == evaluation_id


async def test_confirming_a_missing_or_outdated_case_is_refused_when_the_evaluation_is_current(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks)

    for case in ["missing", "outdated"]:
        assert (await generate(client, application["id"], evaluation_case=case)).status_code == 409
    assert (await cover_letter(client, application["id"]))["generation"] is None


async def test_a_failed_generation_leaves_the_letter_unchanged_shows_why_and_can_be_retried(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks)
    fake_llm.cover_letter.respond_with(a_letter(letter="The first draft."))
    await generate(client, application["id"])
    await run_queued_tasks()
    first = (await cover_letter(client, application["id"]))["draft"]

    fake_llm.cover_letter.respond_with(Failure("error", "Overloaded"))
    await generate(client, application["id"], instruction="Shorter.")
    await run_queued_tasks()

    letter = await cover_letter(client, application["id"])
    assert letter["draft"] == first
    assert letter["generation"]["status"] == "failed"
    assert letter["generation"]["failure"] == {"kind": "error", "reason": "Overloaded"}
    assert letter["generation"]["instruction"] == "Shorter."
    assert letter["generation"]["draft_id"] is None

    fake_llm.cover_letter.respond_with(a_letter(letter="The retried draft."))
    retried = await generate(client, application["id"], instruction="Shorter.")
    assert retried.status_code == 201
    await run_queued_tasks()

    letter = await cover_letter(client, application["id"])
    assert letter["generation"]["status"] == "done"
    assert letter["generation"]["draft_id"] == letter["draft"]["id"]
    assert letter["draft"]["text"] == "The retried draft."
    assert letter["draft"]["instruction"] == "Shorter."


async def test_a_blank_letter_is_a_malformed_answer(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks)
    fake_llm.cover_letter.respond_with(a_letter(letter="  \n"))

    await generate(client, application["id"])
    await run_queued_tasks()

    letter = await cover_letter(client, application["id"])
    assert letter["draft"] is None
    assert letter["generation"]["failure"]["kind"] == "malformed"


async def test_generating_is_refused_while_a_request_is_under_way_unless_it_is_stuck(
    client: httpx.AsyncClient,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
    make_stuck: Callable[[str, int], None],
) -> None:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks)
    await generate(client, application["id"])
    under_way = (await cover_letter(client, application["id"]))["generation"]

    assert (await generate(client, application["id"])).status_code == 409

    assert under_way["stuck"] is False
    make_stuck("cover_letter_generations", under_way["id"])
    assert (await cover_letter(client, application["id"]))["generation"]["stuck"] is True
    assert (await generate(client, application["id"])).status_code == 201
    await run_queued_tasks()

    letter = await cover_letter(client, application["id"])
    assert letter["generation"]["status"] == "done"
    assert len(letter["drafts"]) == 1  # the stuck request wrote none


async def test_generating_is_refused_unless_the_application_is_preparing(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks)

    for state in ["applied", "interview_loop", "rejected"]:
        await move(client, application["id"], state)
        refused = await generate(client, application["id"])
        assert refused.status_code == 409
        assert (await cover_letter(client, application["id"]))["editable"] is False
    await move(client, application["id"], "preparing")

    assert (await cover_letter(client, application["id"]))["editable"] is True
    assert (await generate(client, application["id"])).status_code == 201


async def test_an_application_that_leaves_preparing_before_the_generation_runs_gets_no_draft(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks)
    await generate(client, application["id"])
    await move(client, application["id"], "applied")

    await run_queued_tasks()

    letter = await cover_letter(client, application["id"])
    assert letter["draft"] is None
    assert letter["generation"]["status"] == "failed"
    assert letter["generation"]["failure"]["kind"] == "locked"
    assert fake_llm.cover_letter.calls == []


async def test_generating_is_refused_while_there_is_no_career_profile(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks)
    await write_career_profile(client, "  ")

    refused = await generate(client, application["id"])

    assert refused.status_code == 409
    assert "Career Profile" in refused.json()["detail"]


async def test_the_writing_guide_is_not_required(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks)

    await generate(client, application["id"])
    await run_queued_tasks()

    draft = (await cover_letter(client, application["id"]))["draft"]
    assert draft["writing_guide_version_id"] is None
    assert draft["writing_guide_version_number"] is None
    assert "no Writing Guide" in sent(fake_llm)


async def test_the_cover_letter_of_an_unknown_or_deleted_application_is_not_found(
    client: httpx.AsyncClient, fake_llm: FakeLlm, run_queued_tasks: RunTasks
) -> None:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks)
    await client.delete(f"/api/applications/{application['id']}")

    for application_id in [999, application["id"]]:
        url = f"/api/applications/{application_id}/cover-letter"
        assert (await client.get(url)).status_code == 404
        assert (await generate(client, application_id)).status_code == 404


async def test_a_posting_edited_after_the_request_makes_the_draft_record_an_outdated_case(
    client: httpx.AsyncClient,
    settings: Settings,
    fake_llm: FakeLlm,
    run_queued_tasks: RunTasks,
) -> None:
    await write_career_profile(client)
    application = await started_application(client, fake_llm, run_queued_tasks, "Data Engineer")
    evaluation_id = (await current_evaluation(client, application["job_posting_id"]))["id"]
    assert (await generate(client, application["id"], evaluation_case="current")).status_code == 201
    await edit_posting_text(
        settings,
        application["job_posting_id"],
        title="Staff Data Engineer",
        description="Lead the data platform team.",
    )

    await run_queued_tasks()

    # The flags of the Evaluation confirmed, with the posting as it is when the draft is written
    assert "Python pipelines are the core of their experience." in sent(fake_llm)
    assert "Lead the data platform team." in sent(fake_llm)
    draft = (await cover_letter(client, application["id"]))["draft"]
    assert draft["evaluation_case"] == "outdated"
    assert draft["evaluation_id"] == evaluation_id
