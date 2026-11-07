"""The columns every LLM run's table shares: its status, timestamps, model and failure."""

import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import CheckConstraint, String, func
from sqlalchemy.orm import Mapped, mapped_column

from job_scout.llm.interface import FailureKind

# Queued until the worker picks it up, running while it calls the LLM, then done or failed
RunStatus = Literal["queued", "running", "done", "failed"]

# Why a run failed: its LLM call failed; the feature refused it, for an input the user has
# to write first or a target that no longer takes its result; or it was stuck and replaced
RunFailureKind = FailureKind | Literal["missing_input", "locked", "stuck"]


class LlmRun:
    """One run of an LLM task, mixed into the feature's own table.

    A feature narrows `status` to its own statuses, which include every `RunStatus`.
    """

    # Whose Provider key the run is made with; each feature's table indexes it
    owner_id: Mapped[uuid.UUID]

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String)
    queued_at: Mapped[datetime] = mapped_column(server_default=func.now())
    started_at: Mapped[datetime | None]  # when its first attempt started
    finished_at: Mapped[datetime | None]

    # The last LLM call it made; null when it made none
    model: Mapped[str | None]
    prompt_version: Mapped[str | None]

    # Once failed
    failure_kind: Mapped[RunFailureKind | None] = mapped_column(String)
    failure_reason: Mapped[str | None]


def failure_complete() -> CheckConstraint:
    """The constraint every run table carries: a failure has both a kind and a reason."""
    return CheckConstraint(
        "(failure_kind IS NULL) = (failure_reason IS NULL)", name="failure_complete"
    )
