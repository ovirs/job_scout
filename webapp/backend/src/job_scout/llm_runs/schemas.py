from pydantic import BaseModel

from job_scout.llm.interface import ModelChoice
from job_scout.llm_runs.models import LlmRun, RunFailureKind
from job_scout.settings.schemas import ModelChoiceBody


class LlmRunFailureRead(BaseModel):
    """Why an LLM run failed."""

    kind: RunFailureKind
    reason: str

    @classmethod
    def of(cls, run: LlmRun) -> "LlmRunFailureRead | None":
        if run.failure_kind is None or run.failure_reason is None:
            return None
        return cls(kind=run.failure_kind, reason=run.failure_reason)


class LlmRunStart(BaseModel):
    """The model choice of a run the user starts. Left out, the run takes the step's default
    (a Clipping retry, the one it was read with); refused when the model cannot be used."""

    model_choice: ModelChoiceBody | None = None

    def choice(self) -> ModelChoice | None:
        return None if self.model_choice is None else self.model_choice.choice()


def model_choice_read(run: LlmRun) -> ModelChoiceBody | None:
    """The model choice a run was queued with, if it had one."""
    requested = run.requested
    return None if requested is None else ModelChoiceBody.of(requested)
