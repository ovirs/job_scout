"""The thin internal interface every LLM call goes through; see `job_scout.llm.interface`.

The interface sits below every package. The adapters (`anthropic_adapter`,
`openai_adapter`, `gemini_adapter`, and `fake` for tests) know each step's types, so they
sit above every package, with the app and the worker that hand them in.
"""

from job_scout.llm.interface import Failure, FailureKind, Llm, Outcome

__all__ = ["Failure", "FailureKind", "Llm", "Outcome"]
