"""The background task that runs an Evaluation with the LLM: an LLM run (see `llm_runs`).

Each attempt reads the user inputs and posting afresh. A result failing a check is a
failed call, retried like any other.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from job_scout.evaluations import domain as evaluations
from job_scout.evaluations.domain import CheckedResult, Inputs
from job_scout.evaluations.models import Evaluation
from job_scout.llm.interface import Llm, Outcome, Step
from job_scout.llm_runs.domain import Refusal


class EvaluationTask:
    """Judges the posting against the current user inputs and stores the gated result."""

    task_name = "evaluate"
    run_type = Evaluation
    step: Step = "evaluation"

    async def gather(self, session: AsyncSession, run: Evaluation) -> Inputs | Refusal:
        inputs = await evaluations.gather(session, run)
        missing = inputs.missing()
        # Retrying would not help: the user has to write the input first
        return inputs if missing is None else Refusal("missing_input", missing)

    async def call(self, llm: Llm, inputs: Inputs) -> Outcome[CheckedResult]:
        return evaluations.check(await llm.evaluate(inputs.prompt()), inputs)

    async def record(
        self, session: AsyncSession, run: Evaluation, inputs: Inputs, result: CheckedResult
    ) -> Refusal | None:
        evaluations.record(run, result)
        return None


EVALUATION = EvaluationTask()
