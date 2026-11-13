"""The LLM run: one lifecycle for every background task that calls the LLM.

A feature stores a queued run in its own table (with the `LlmRun` columns) and hands
it here with its `LlmRunTask`, which only gathers the inputs, calls the LLM and records
the result. This module owns the rest:

- queueing: a run the user starts takes the model choice they gave, or else the one it
  was queued with before (a run queued again in place) or its step's default, and is
  refused when that cannot be used; a run that starts on its own takes its step's
  default. It is enqueued after the commit that stores it; a run that starts on its own
  whose default cannot be used, or a run whose enqueue fails, is failed at once, so the
  user can fix Settings or retry it;
- the status, from queued to running to done or failed, and its timestamps;
- attempts: a failed call, or an unexpected error, is retried on the queue, and only
  the last attempt's failure is stored; a call the Provider rejected as invalid is not
  retried, since the same request would be rejected again;
- refusals: the task may refuse a run before the call (an input is missing) or after it
  (its target no longer takes the result), failing it without a retry;
- the Provider: every attempt calls the run's model choice with the run owner's key for
  its Provider, read afresh, so a replaced key takes effect on the next attempt; a run
  whose owner has no key is failed without a retry;
- one policy for runs under way: a feature never starts a second run of the same thing
  while one is under way, unless that one is stuck, queued or running for longer than
  `STUCK_AFTER`. A stuck run is failed and replaced, or requeued in place.

No transaction is held open while the LLM call runs.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import procrastinate
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from job_scout.config import Settings
from job_scout.llm.interface import (
    Connect,
    Failure,
    FailureKind,
    Llm,
    ModelChoice,
    ModelLister,
    Outcome,
    Provider,
    Step,
)
from job_scout.llm_runs.models import LlmRun, RunFailureKind
from job_scout.settings import domain as provider_settings

logger = logging.getLogger(__name__)

# A failed call of these kinds fails the run at once: the Provider refused the request as
# invalid, and would refuse it again
NOT_RETRIED: frozenset[FailureKind] = frozenset({"rejected"})

# A run calls the LLM at most this many times before it records the failure
ATTEMPTS = 3

# A run queued or running for longer than this is stuck: its worker died, say. Well above
# the longest a run takes, every attempt timing out and waiting before the next.
STUCK_AFTER = timedelta(hours=1)

UNDER_WAY = ("queued", "running")


@dataclass(frozen=True)
class Refusal:
    """Why a task will not run, or not store its result: the run fails, with no retry."""

    kind: RunFailureKind
    reason: str


class LlmRunTask[R: LlmRun, I, T](Protocol):
    """What a feature supplies for its runs: how to gather the inputs, call the LLM and
    record the result. The lifecycle does the rest."""

    @property
    def task_name(self) -> str:
        """The run's task on the queue."""
        ...

    @property
    def run_type(self) -> type[R]:
        """The table its runs are stored in."""
        ...

    @property
    def step(self) -> Step:
        """The LLM step it calls, whose default model choice its runs take."""
        ...

    async def gather(self, session: AsyncSession, run: R) -> I | Refusal:
        """What the run is made from, read in the transaction that marks it running; or why
        it cannot run. Called afresh on every attempt."""
        ...

    async def call(self, llm: Llm, inputs: I) -> Outcome[T]:
        """The LLM call, with the answer checked: a result failing a check is a failure."""
        ...

    async def record(self, session: AsyncSession, run: R, inputs: I, result: T) -> Refusal | None:
        """Store the result on the run, in the transaction that marks it done; or why it no
        longer can, storing nothing."""
        ...


class RunUnderWay(Exception):
    """A run of the same thing is queued or running, and not stuck."""


class NotRetryable(Exception):
    """Only a failed or a stuck run can be requeued."""


class LlmCallFailed(Exception):
    """Raised to have the queue retry a run whose LLM call failed."""


# Any task, whatever its run, inputs and result
type AnyTask = LlmRunTask[Any, Any, Any]

# A task body: the queue's context for it, and the run's id it was enqueued with
type TaskBody = Callable[[procrastinate.JobContext, int], Awaitable[None]]


def register(task_queue: procrastinate.App, settings: Settings, tasks: Iterable[AnyTask]) -> None:
    """Register each task on the queue, retried up to `ATTEMPTS` runs in all."""
    retry = procrastinate.RetryStrategy(
        max_attempts=ATTEMPTS - 1,  # retries after the first run
        wait=settings.llm_retry_wait_seconds,
    )
    for task in tasks:
        task_queue.task(name=task.task_name, pass_context=True, retry=retry)(_task_body(task))


def _task_body(task: AnyTask) -> TaskBody:
    async def body(context: procrastinate.JobContext, run_id: int) -> None:
        await execute(context, task, run_id)

    return body


async def commit_and_enqueue(
    session: AsyncSession,
    task_queue: procrastinate.App,
    lister: ModelLister,
    task: AnyTask,
    *runs: LlmRun,
) -> None:
    """Give each queued run with no model choice its step's default, commit the session,
    which holds the runs, then put each on the queue. A run the user started has its
    choice already, from `choose`.

    A run whose default cannot be used is failed at once, pointing to Settings, and never
    queued: it never switches to another model. A run whose enqueue fails is failed with
    the reason, so the user can retry it rather than wait for it to count as stuck.
    """
    for run in runs:
        if run.requested is None:
            await _choose_default(session, lister, task.step, run)
    await session.commit()
    for run in runs:
        if run.status != "queued":
            continue
        try:
            await task_queue.configure_task(task.task_name).defer_async(run_id=run.id)
        except Exception as error:
            logger.exception("Could not queue run %s of %s", run.id, task.task_name)
            _fail(run, "error", f"Could not queue the run: {error!r}")
            await session.commit()


async def choose(
    session: AsyncSession,
    lister: ModelLister,
    task: AnyTask,
    run: LlmRun,
    given: ModelChoice | None,
) -> None:
    """Store on a queued run the user started the model choice it calls, before
    `commit_and_enqueue`: the one given; without one, the one it was queued with before,
    for a run queued again in place; else its step's default.

    Raises `settings.NotUsable` when the choice given cannot be used, and
    `settings.NoUsableChoice` when the one taken without it cannot; the caller then
    commits nothing.
    """
    run.requested = await provider_settings.run_choice(
        session,
        lister,
        owner_id=run.owner_id,
        step=task.step,
        given=given,
        kept=run.requested,
    )


async def _choose_default(
    session: AsyncSession, lister: ModelLister, step: Step, run: LlmRun
) -> None:
    """Store the step's default on the run as its choice; fail it, without a call, when the
    default cannot be used."""
    default = await provider_settings.default(session, lister, owner_id=run.owner_id, step=step)
    run.requested = default.choice
    if default.problem is not None:
        _refuse(
            run,
            Refusal(
                "missing_input",
                f"The default model for this step cannot be used: {default.problem}."
                " Choose another in Settings",
            ),
        )


async def execute[R: LlmRun, I, T](
    context: procrastinate.JobContext, task: LlmRunTask[R, I, T], run_id: int
) -> None:
    """One attempt of a run: gather, call the LLM, record. A run no longer under way, done
    or failed or replaced as stuck, is left as it is.

    An unexpected error anywhere (a bug, say) is retried like a failed call, and the last
    attempt's is stored, so it never leaves the run under way for good.
    """
    sessions: async_sessionmaker[AsyncSession] = context.additional_context["sessions"]
    connect: Connect = context.additional_context["connect"]
    last_attempt = _is_last_attempt(context)
    try:
        await _attempt(sessions, connect, task, run_id, last_attempt)
    except LlmCallFailed:
        raise
    except Exception as error:
        if not last_attempt:
            raise
        async with sessions.begin() as session:
            run = await _locked_if_under_way(session, task, run_id)
            if run is not None:
                run.provider = run.model = run.prompt_version = None
                _fail(run, "error", f"Unexpected error: {error!r}")


async def _attempt[R: LlmRun, I, T](
    sessions: async_sessionmaker[AsyncSession],
    connect: Connect,
    task: LlmRunTask[R, I, T],
    run_id: int,
    last_attempt: bool,
) -> None:
    async with sessions.begin() as session:
        run = await _locked_if_under_way(session, task, run_id)
        if run is None:
            return
        # Tells this attempt's run from the same run requeued while the LLM answered
        queued_at = run.queued_at
        run.status = "running"
        run.started_at = run.started_at or _now()
        gathered = await task.gather(session, run)
        if isinstance(gathered, Refusal):
            _refuse(run, gathered)
            return
        choice = run.requested
        if choice is None:
            _refuse(
                run, Refusal("missing_input", "The run has no model chosen: choose one in Settings")
            )
            return
        api_key = await _api_key(session, run.owner_id, choice.provider)
        if isinstance(api_key, Refusal):
            _refuse(run, api_key)
            return
    outcome = await task.call(connect(choice, api_key, run.owner_id), gathered)
    result = outcome.result
    if isinstance(result, Failure) and result.kind not in NOT_RETRIED and not last_attempt:
        raise LlmCallFailed(result.reason)
    async with sessions.begin() as session:
        run = await _locked_if_under_way(session, task, run_id, queued_at)
        if run is None:
            return
        run.provider = outcome.provider
        run.model = outcome.model
        run.prompt_version = outcome.prompt_version
        if isinstance(result, Failure):
            _fail(run, result.kind, result.reason)
            return
        refusal = await task.record(session, run, gathered, result)
        if refusal is not None:
            _fail(run, refusal.kind, refusal.reason)
            return
        run.status = "done"
        run.finished_at = _now()
        run.failure_kind = run.failure_reason = None


async def _api_key(session: AsyncSession, owner_id: uuid.UUID, provider: Provider) -> str | Refusal:
    """The owner's key for the Provider, read afresh for each attempt; or a refusal
    pointing to Settings when they have none."""
    api_key = await provider_settings.api_key(session, owner_id=owner_id, provider=provider)
    if api_key is None:
        name = provider_settings.PROVIDER_NAMES[provider]
        return Refusal("missing_input", f"There is no API key for {name}: add one in Settings")
    return api_key


async def _locked_if_under_way[R: LlmRun](
    session: AsyncSession,
    task: LlmRunTask[R, Any, Any],
    run_id: int,
    queued_at: datetime | None = None,
) -> R | None:
    """The run, locked until the transaction ends; None once it is no longer under way, or
    when it was requeued since `queued_at`."""
    run = await session.get_one(task.run_type, run_id, with_for_update=True)
    if run.status not in UNDER_WAY or queued_at not in (None, run.queued_at):
        return None
    return run


def under_way(run: LlmRun) -> bool:
    return run.status in UNDER_WAY


def stuck(run: LlmRun) -> bool:
    """Whether the run has been queued or running for longer than any run takes."""
    since = run.started_at or run.queued_at
    return under_way(run) and since < _now() - STUCK_AFTER


def clear_the_way(runs: Sequence[LlmRun]) -> None:
    """Before a new run of the same thing as `runs`: refused while one of them is under way
    and not stuck; a stuck one is failed, so it is replaced."""
    if any(under_way(run) and not stuck(run) for run in runs):
        raise RunUnderWay
    for run in runs:
        if stuck(run):
            _fail(run, "stuck", "The run was stuck and was replaced by a new one")


def requeue(run: LlmRun) -> None:
    """Make a failed or stuck run queued again, as if new; the caller commits and enqueues
    it. A stuck run's worker may still be at it: what it finds is not recorded."""
    if under_way(run) and not stuck(run):
        raise RunUnderWay
    if not under_way(run) and run.status != "failed":
        raise NotRetryable
    run.status = "queued"
    run.queued_at = _now()
    run.started_at = run.finished_at = None
    run.failure_kind = run.failure_reason = None


def _refuse(run: LlmRun, refusal: Refusal) -> None:
    """Fail a run before its call; retrying would not help, as the feature or the Settings
    have to change first."""
    run.provider = run.model = run.prompt_version = None
    _fail(run, refusal.kind, refusal.reason)


def _fail(run: LlmRun, kind: RunFailureKind, reason: str) -> None:
    run.status = "failed"
    run.finished_at = _now()
    run.failure_kind = kind
    run.failure_reason = reason


def _is_last_attempt(context: procrastinate.JobContext) -> bool:
    assert context.job is not None
    return context.job.attempts >= ATTEMPTS - 1  # attempts counts earlier runs


def _now() -> datetime:
    return datetime.now(UTC)
