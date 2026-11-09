"""The columns every LLM run's table shares: its owner, status, timestamps, model and
failure."""

import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import CheckConstraint, String, func
from sqlalchemy.orm import Mapped, mapped_column

from job_scout.llm.interface import FailureKind, ModelChoice, Provider

# Queued until the worker picks it up, running while it calls the LLM, then done or failed
RunStatus = Literal["queued", "running", "done", "failed"]

# Why a run failed: its LLM call failed; the feature refused it, for an input the user has
# to write first or a target that no longer takes its result; or it was stuck and replaced
RunFailureKind = FailureKind | Literal["missing_input", "locked", "stuck"]


class LlmRun:
    """One run of an LLM task, mixed into the feature's own table.

    A feature narrows `status` to its own statuses, which include every `RunStatus`; it
    redeclares no other column.
    """

    id: Mapped[int] = mapped_column(primary_key=True)
    # Whose run it is, and so whose Provider keys it calls the LLM with
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String)
    queued_at: Mapped[datetime] = mapped_column(server_default=func.now())
    started_at: Mapped[datetime | None]  # when its first attempt started
    finished_at: Mapped[datetime | None]

    # The model choice it was queued with; null when it had none to take (no default was
    # chosen, or it ran before choices were stored and never called the LLM)
    requested_provider: Mapped[Provider | None] = mapped_column(String)
    requested_model: Mapped[str | None]
    requested_effort: Mapped[str | None]  # null also for the Provider's default

    # The last LLM call it made: the Provider that answered, and the model it reported;
    # null when it made none
    provider: Mapped[Provider | None] = mapped_column(String)
    model: Mapped[str | None]
    prompt_version: Mapped[str | None]

    # Once failed
    failure_kind: Mapped[RunFailureKind | None] = mapped_column(String)
    failure_reason: Mapped[str | None]

    @property
    def requested(self) -> ModelChoice | None:
        """The model choice it was queued with, if it had one."""
        if self.requested_provider is None or self.requested_model is None:
            return None
        return ModelChoice(
            provider=self.requested_provider,
            model=self.requested_model,
            effort=self.requested_effort,
        )

    @requested.setter
    def requested(self, choice: ModelChoice | None) -> None:
        self.requested_provider = None if choice is None else choice.provider
        self.requested_model = None if choice is None else choice.model
        self.requested_effort = None if choice is None else choice.effort


def failure_complete() -> CheckConstraint:
    """The constraint every run table carries: a failure has both a kind and a reason."""
    return CheckConstraint(
        "(failure_kind IS NULL) = (failure_reason IS NULL)", name="failure_complete"
    )
