"""The thin internal interface every LLM call goes through; see `job_scout.llm.interface`."""

from job_scout.llm.anthropic_adapter import AnthropicLlm
from job_scout.llm.interface import Failure, FailureKind, Llm, Outcome

__all__ = ["AnthropicLlm", "Failure", "FailureKind", "Llm", "Outcome"]
