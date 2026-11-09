"""The background worker: runs every queued task. Start with `python -m job_scout.worker`."""

import asyncio
import logging

from job_scout import queue, tables  # noqa: F401  # tables: registers every table
from job_scout.config import Settings
from job_scout.llm import providers
from job_scout.llm.interface import Connect
from job_scout.runtime import open_runtime


async def run(settings: Settings, *, connect: Connect | None = None, wait: bool = True) -> None:
    """Run queued tasks; with `wait=False`, return once the queue is empty.

    Each LLM call goes to the API of the run's Provider with the run owner's key, read
    afresh for every attempt, unless another `connect` is given.
    """
    connect = connect or providers.connect
    async with open_runtime(settings) as runtime:
        await runtime.task_queue.run_worker_async(
            additional_context=queue.worker_context(runtime.sessions, connect),
            wait=wait,
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run(Settings()))
