from pydantic import BaseModel

from job_scout.llm_runs.models import LlmRun, RunFailureKind


class LlmRunFailureRead(BaseModel):
    """Why an LLM run failed."""

    kind: RunFailureKind
    reason: str

    @classmethod
    def of(cls, run: LlmRun) -> "LlmRunFailureRead | None":
        if run.failure_kind is None or run.failure_reason is None:
            return None
        return cls(kind=run.failure_kind, reason=run.failure_reason)
