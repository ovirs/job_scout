"""The LLM run lifecycle, tested once for every feature: a test-only task on a test-only
table, run through the real queue and worker, with the fake LLM."""

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime, timedelta

import pytest
from clipping_helpers import an_extraction
from conftest import TEST_KEY
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from job_scout import db, queue
from job_scout.clippings.extraction import ManualEntryExtraction
from job_scout.config import Settings
from job_scout.llm.fake import FakeLlm, FakeModelLister
from job_scout.llm.interface import STEPS, Failure, Llm, ModelChoice, Outcome, Step
from job_scout.llm_runs import domain as llm_runs
from job_scout.llm_runs.models import LlmRun, RunStatus, failure_complete
from job_scout.owners import LOCAL_USER_ID
from job_scout.settings import domain as provider_settings

# The default model choice of every step for the runs' owner
CHOICE = ModelChoice(provider="anthropic", model="claude-opus-5-5", effort="high")


class ExampleBase(DeclarativeBase):
    """Kept off the app's metadata, so the migrations check never sees the test table."""

    type_annotation_map = db.Base.type_annotation_map


class ExampleRun(ExampleBase, LlmRun):
    __tablename__ = "example_runs"
    __table_args__ = (failure_complete(),)

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[RunStatus] = mapped_column()
    subject: Mapped[str]
    answer: Mapped[str | None]


class ExampleTask:
    """Reads `subject` with the extraction step and stores the title it answers.

    A subject of "missing" is refused before the call; an answer titled "locked" is
    refused after it.
    """

    task_name = "example_run"
    run_type = ExampleRun
    step: Step = "extraction"

    def __init__(self, during_call: Callable[[], Awaitable[None]] | None = None) -> None:
        self._during_call = during_call  # runs while the LLM is answering

    async def gather(self, session: AsyncSession, run: ExampleRun) -> str | llm_runs.Refusal:
        if run.subject == "broken":
            raise RuntimeError("a bug in gathering")
        if run.subject == "missing":
            return llm_runs.Refusal("missing_input", "Write the subject first")
        return run.subject

    async def call(self, llm: Llm, inputs: str) -> Outcome[ManualEntryExtraction]:
        outcome = await llm.extract_manual_entry(inputs)
        if self._during_call is not None:
            await self._during_call()
        return outcome

    async def record(
        self, session: AsyncSession, run: ExampleRun, inputs: str, result: ManualEntryExtraction
    ) -> llm_runs.Refusal | None:
        if result.title == "locked":
            return llm_runs.Refusal("locked", "The target no longer takes a result")
        run.answer = result.title
        return None


TASK = ExampleTask()


@pytest.fixture
async def sessions(settings: Settings) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = db.create_engine(settings)
    async with engine.begin() as connection:
        await connection.run_sync(ExampleBase.metadata.create_all)
    sessions = db.create_sessionmaker(engine)
    async with sessions() as session:  # the runs' owner has set up Anthropic and defaults
        await provider_settings.save_key(
            session,
            FakeModelLister(),
            owner_id=LOCAL_USER_ID,
            provider="anthropic",
            api_key=TEST_KEY,
        )
        await provider_settings.save_defaults(
            session,
            FakeModelLister(),
            owner_id=LOCAL_USER_ID,
            choices=dict.fromkeys(STEPS, CHOICE),
        )
    yield sessions
    await engine.dispose()


@pytest.fixture
def queue_runs(
    settings: Settings, sessions: async_sessionmaker[AsyncSession]
) -> Callable[..., Awaitable[list[int]]]:
    """Store a queued run for each subject and enqueue it; returns their ids."""

    async def store(*subjects: str) -> list[int]:
        task_queue = queue.build(settings)
        async with task_queue.open_async(), sessions() as session:
            runs = [
                ExampleRun(owner_id=LOCAL_USER_ID, subject=subject, status="queued")
                for subject in subjects
            ]
            session.add_all(runs)
            await llm_runs.commit_and_enqueue(session, task_queue, FakeModelLister(), TASK, *runs)
            return [run.id for run in runs]

    return store


@pytest.fixture
def run_worker(
    settings: Settings, sessions: async_sessionmaker[AsyncSession], fake_llm: FakeLlm
) -> Callable[..., Awaitable[None]]:
    """Run every queued example run to completion, retries included."""

    async def run(task: ExampleTask = TASK) -> None:
        task_queue = queue.build(settings)
        llm_runs.register(task_queue, settings, [task])
        async with task_queue.open_async():
            await task_queue.run_worker_async(
                additional_context=queue.worker_context(sessions, fake_llm.connect), wait=False
            )

    return run


async def a_run(sessions: async_sessionmaker[AsyncSession], run_id: int) -> ExampleRun:
    async with sessions() as session:
        return await session.get_one(ExampleRun, run_id)


async def test_a_run_the_llm_answers_is_done_with_its_result_choice_model_and_times(
    sessions: async_sessionmaker[AsyncSession],
    fake_llm: FakeLlm,
    queue_runs: Callable[..., Awaitable[list[int]]],
    run_worker: Callable[..., Awaitable[None]],
) -> None:
    fake_llm.manual_entry_extraction.respond_with(an_extraction(title="Data Engineer"))
    [run_id] = await queue_runs("a pasted posting")

    await run_worker()

    run = await a_run(sessions, run_id)
    assert run.status == "done"
    assert run.answer == "Data Engineer"
    assert run.requested == CHOICE  # its step's default when it was queued
    assert (run.provider, run.model) == ("anthropic", "claude-opus-5-5")  # what answered
    assert run.prompt_version is not None
    assert run.failure_kind is None
    assert isinstance(run.started_at, datetime) and isinstance(run.finished_at, datetime)
    assert run.queued_at <= run.started_at <= run.finished_at
    assert fake_llm.manual_entry_extraction.calls == ["a pasted posting"]
    assert fake_llm.connections == [(CHOICE, TEST_KEY)]


async def test_a_call_the_provider_rejected_fails_the_run_at_once_without_a_retry(
    sessions: async_sessionmaker[AsyncSession],
    fake_llm: FakeLlm,
    queue_runs: Callable[..., Awaitable[list[int]]],
    run_worker: Callable[..., Awaitable[None]],
) -> None:
    fake_llm.manual_entry_extraction.respond_with(
        Failure("rejected", "effort: Input should be 'low', 'medium' or 'high'"), an_extraction()
    )
    [run_id] = await queue_runs("a pasted posting")

    await run_worker()
    await run_worker()  # nothing is left on the queue

    run = await a_run(sessions, run_id)
    assert run.status == "failed"
    assert (run.failure_kind, run.failure_reason) == (
        "rejected",
        "effort: Input should be 'low', 'medium' or 'high'",
    )
    assert (run.provider, run.model) == ("anthropic", "claude-opus-5-5")
    assert len(fake_llm.manual_entry_extraction.calls) == 1


async def test_a_run_whose_default_cannot_be_used_fails_when_queued_without_a_call(
    sessions: async_sessionmaker[AsyncSession],
    fake_llm: FakeLlm,
    queue_runs: Callable[..., Awaitable[list[int]]],
    run_worker: Callable[..., Awaitable[None]],
) -> None:
    async with sessions() as session:
        await provider_settings.remove_key(session, owner_id=LOCAL_USER_ID, provider="anthropic")
    [run_id] = await queue_runs("a pasted posting")
    await run_worker()

    run = await a_run(sessions, run_id)
    assert run.status == "failed"
    assert run.started_at is None and run.finished_at is not None
    assert (run.failure_kind, run.failure_reason) == (
        "missing_input",
        "The default model for this step cannot be used: There is no API key for Anthropic."
        " Choose another in Settings",
    )
    assert run.requested == CHOICE  # kept, to show what could not be used
    assert fake_llm.connections == []


async def test_a_failed_call_is_retried_and_a_later_answer_is_kept(
    sessions: async_sessionmaker[AsyncSession],
    fake_llm: FakeLlm,
    queue_runs: Callable[..., Awaitable[list[int]]],
    run_worker: Callable[..., Awaitable[None]],
) -> None:
    overloaded = Failure("error", "The Anthropic API is overloaded")
    fake_llm.manual_entry_extraction.respond_with(overloaded, overloaded, an_extraction())
    [run_id] = await queue_runs("a pasted posting")

    await run_worker()

    run = await a_run(sessions, run_id)
    assert (run.status, run.failure_kind, run.answer) == ("done", None, "Senior Data Engineer")
    assert len(fake_llm.manual_entry_extraction.calls) == 3


async def test_after_three_failed_calls_the_run_fails_with_the_last_reason(
    sessions: async_sessionmaker[AsyncSession],
    fake_llm: FakeLlm,
    queue_runs: Callable[..., Awaitable[list[int]]],
    run_worker: Callable[..., Awaitable[None]],
) -> None:
    fake_llm.manual_entry_extraction.respond_with(
        Failure("error", "Overloaded"),
        Failure("malformed", "Not the step's shape"),
        Failure("refusal", "The model declined"),
    )
    [run_id] = await queue_runs("a pasted posting")

    await run_worker()
    await run_worker()  # nothing is left on the queue

    run = await a_run(sessions, run_id)
    assert run.status == "failed"
    assert (run.failure_kind, run.failure_reason) == ("refusal", "The model declined")
    assert run.model == "claude-opus-5-5"  # the call that failed
    assert run.finished_at is not None
    assert run.answer is None
    assert len(fake_llm.manual_entry_extraction.calls) == 3


async def test_an_unexpected_error_is_retried_then_fails_the_run_naming_no_model(
    sessions: async_sessionmaker[AsyncSession],
    fake_llm: FakeLlm,
    queue_runs: Callable[..., Awaitable[list[int]]],
    run_worker: Callable[..., Awaitable[None]],
) -> None:
    fake_llm.manual_entry_extraction.respond_with(RuntimeError("connection reset"))
    [run_id] = await queue_runs("a pasted posting")

    await run_worker()

    run = await a_run(sessions, run_id)
    assert (run.status, run.failure_kind) == ("failed", "error")
    assert "connection reset" in (run.failure_reason or "")
    assert (run.model, run.prompt_version) == (None, None)
    assert len(fake_llm.manual_entry_extraction.calls) == 3


async def test_a_run_refused_before_the_call_fails_at_once_without_calling_the_llm(
    sessions: async_sessionmaker[AsyncSession],
    fake_llm: FakeLlm,
    queue_runs: Callable[..., Awaitable[list[int]]],
    run_worker: Callable[..., Awaitable[None]],
) -> None:
    [run_id] = await queue_runs("missing")

    await run_worker()

    run = await a_run(sessions, run_id)
    assert run.status == "failed"
    assert (run.failure_kind, run.failure_reason) == ("missing_input", "Write the subject first")
    assert run.started_at is not None and run.finished_at is not None
    assert fake_llm.manual_entry_extraction.calls == []


async def test_a_result_refused_after_the_call_is_not_stored_and_is_not_retried(
    sessions: async_sessionmaker[AsyncSession],
    fake_llm: FakeLlm,
    queue_runs: Callable[..., Awaitable[list[int]]],
    run_worker: Callable[..., Awaitable[None]],
) -> None:
    fake_llm.manual_entry_extraction.respond_with(an_extraction(title="locked"))
    [run_id] = await queue_runs("a pasted posting")

    await run_worker()

    run = await a_run(sessions, run_id)
    assert (run.status, run.failure_kind) == ("failed", "locked")
    assert run.answer is None
    assert run.model == "claude-opus-5-5"
    assert len(fake_llm.manual_entry_extraction.calls) == 1


async def test_a_run_no_longer_under_way_is_left_as_it_is(
    sessions: async_sessionmaker[AsyncSession],
    fake_llm: FakeLlm,
    queue_runs: Callable[..., Awaitable[list[int]]],
    run_worker: Callable[..., Awaitable[None]],
) -> None:
    [run_id] = await queue_runs("a pasted posting")
    async with sessions.begin() as session:
        (await session.get_one(ExampleRun, run_id)).status = "done"

    await run_worker()

    assert (await a_run(sessions, run_id)).started_at is None
    assert fake_llm.manual_entry_extraction.calls == []


async def make_stuck(sessions: async_sessionmaker[AsyncSession], run_id: int) -> None:
    """Make the run look queued or running for longer than any run takes."""
    async with sessions.begin() as session:
        run = await session.get_one(ExampleRun, run_id)
        long_ago = run.queued_at - llm_runs.STUCK_AFTER - timedelta(minutes=1)
        run.queued_at = long_ago
        run.started_at = run.started_at and long_ago


async def test_a_new_run_waits_for_one_under_way_unless_it_is_stuck(
    sessions: async_sessionmaker[AsyncSession],
    queue_runs: Callable[..., Awaitable[list[int]]],
) -> None:
    [run_id] = await queue_runs("a pasted posting")

    async with sessions() as session:
        with pytest.raises(llm_runs.RunUnderWay):
            llm_runs.clear_the_way([await session.get_one(ExampleRun, run_id)])

    await make_stuck(sessions, run_id)
    async with sessions.begin() as session:
        llm_runs.clear_the_way([await session.get_one(ExampleRun, run_id)])

    run = await a_run(sessions, run_id)
    assert (run.status, run.failure_kind) == ("failed", "stuck")


async def test_a_failed_or_stuck_run_is_requeued_in_place_and_runs_again(
    sessions: async_sessionmaker[AsyncSession],
    fake_llm: FakeLlm,
    settings: Settings,
    queue_runs: Callable[..., Awaitable[list[int]]],
    run_worker: Callable[..., Awaitable[None]],
) -> None:
    fake_llm.manual_entry_extraction.respond_with(Failure("refusal", "The model declined"))
    failed, under_way = await queue_runs("a pasted posting", "another posting")
    await run_worker()
    fake_llm.manual_entry_extraction.respond_with(an_extraction())
    async with sessions.begin() as session:
        run = await session.get_one(ExampleRun, under_way)
        run.status, run.failure_kind, run.failure_reason = "running", None, None

    async with sessions() as session:
        with pytest.raises(llm_runs.RunUnderWay):
            llm_runs.requeue(await session.get_one(ExampleRun, under_way))
    await make_stuck(sessions, under_way)
    task_queue = queue.build(settings)
    async with task_queue.open_async(), sessions() as session:
        runs = [await session.get_one(ExampleRun, id) for id in (failed, under_way)]
        for run in runs:
            llm_runs.requeue(run)
            assert (run.status, run.failure_kind, run.started_at) == ("queued", None, None)
        await llm_runs.commit_and_enqueue(session, task_queue, FakeModelLister(), TASK, *runs)
    await run_worker()

    assert [(await a_run(sessions, id)).status for id in (failed, under_way)] == ["done", "done"]


async def test_only_a_failed_or_stuck_run_can_be_requeued(
    sessions: async_sessionmaker[AsyncSession],
    queue_runs: Callable[..., Awaitable[list[int]]],
    run_worker: Callable[..., Awaitable[None]],
) -> None:
    [run_id] = await queue_runs("a pasted posting")
    await run_worker()

    async with sessions() as session:
        with pytest.raises(llm_runs.NotRetryable):
            llm_runs.requeue(await session.get_one(ExampleRun, run_id))


async def test_a_run_replaced_as_stuck_while_the_llm_answered_keeps_its_failure(
    sessions: async_sessionmaker[AsyncSession],
    queue_runs: Callable[..., Awaitable[list[int]]],
    run_worker: Callable[..., Awaitable[None]],
) -> None:
    [run_id] = await queue_runs("a pasted posting")

    async def replace_as_stuck() -> None:
        await make_stuck(sessions, run_id)
        async with sessions.begin() as session:
            llm_runs.clear_the_way([await session.get_one(ExampleRun, run_id)])

    await run_worker(ExampleTask(during_call=replace_as_stuck))

    run = await a_run(sessions, run_id)
    assert (run.status, run.failure_kind, run.answer) == ("failed", "stuck", None)


async def test_a_run_whose_enqueue_fails_is_failed_at_once_so_it_can_be_retried(
    sessions: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    unopened = queue.build(settings)  # deferring on it raises

    async with sessions() as session:
        run = ExampleRun(owner_id=LOCAL_USER_ID, subject="a pasted posting", status="queued")
        session.add(run)
        await llm_runs.commit_and_enqueue(session, unopened, FakeModelLister(), TASK, run)

    stored = await a_run(sessions, run.id)
    assert (stored.status, stored.failure_kind) == ("failed", "error")
    assert "Could not queue the run" in (stored.failure_reason or "")


async def test_an_unexpected_error_outside_the_call_also_fails_the_run_after_retries(
    sessions: async_sessionmaker[AsyncSession],
    fake_llm: FakeLlm,
    queue_runs: Callable[..., Awaitable[list[int]]],
    run_worker: Callable[..., Awaitable[None]],
) -> None:
    [run_id] = await queue_runs("broken")

    await run_worker()

    run = await a_run(sessions, run_id)
    assert (run.status, run.failure_kind) == ("failed", "error")
    assert "a bug in gathering" in (run.failure_reason or "")
    assert fake_llm.manual_entry_extraction.calls == []


async def test_a_stuck_run_requeued_while_the_llm_answered_ignores_the_stale_answer(
    sessions: async_sessionmaker[AsyncSession],
    fake_llm: FakeLlm,
    queue_runs: Callable[..., Awaitable[list[int]]],
    run_worker: Callable[..., Awaitable[None]],
) -> None:
    [run_id] = await queue_runs("a pasted posting")
    fake_llm.manual_entry_extraction.respond_with(an_extraction(title="The stale answer"))

    async def requeue_as_stuck() -> None:
        await make_stuck(sessions, run_id)
        async with sessions.begin() as session:
            llm_runs.requeue(await session.get_one(ExampleRun, run_id))

    await run_worker(ExampleTask(during_call=requeue_as_stuck))

    run = await a_run(sessions, run_id)
    assert (run.status, run.answer) == ("queued", None)  # waits for its new task
