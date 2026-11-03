"""The background worker: runs every queued task. Start with `python -m job_scout.worker`."""

import asyncio
import logging

from job_scout import queue, tables  # noqa: F401  # tables: registers every table
from job_scout.config import Settings
from job_scout.llm.anthropic_adapter import AnthropicLlm
from job_scout.llm.interface import Llm
from job_scout.runtime import open_runtime


async def run(settings: Settings, *, llm: Llm | None = None, wait: bool = True) -> None:
    """Run queued tasks; with `wait=False`, return once the queue is empty.

    LLM calls go to the Anthropic API unless another `llm` is given.
    """
    llm = llm or AnthropicLlm(settings)
    async with open_runtime(settings) as runtime:
        await runtime.task_queue.run_worker_async(
            additional_context=queue.worker_context(runtime.sessions, llm),
            wait=wait,
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run(Settings()))
