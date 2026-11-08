"""What every package's routes get from a request: its database session, the task queue,
the model lister and the owner whose data it touches."""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

import procrastinate
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from job_scout.llm.interface import ModelLister
from job_scout.owners import current_owner


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessions() as session:
        yield session


def get_task_queue(request: Request) -> procrastinate.App:
    task_queue: procrastinate.App = request.app.state.task_queue
    return task_queue


def get_model_lister(request: Request) -> ModelLister:
    model_lister: ModelLister = request.app.state.model_lister
    return model_lister


Session = Annotated[AsyncSession, Depends(get_session)]
TaskQueue = Annotated[procrastinate.App, Depends(get_task_queue)]
Owner = Annotated[uuid.UUID, Depends(current_owner)]
Lister = Annotated[ModelLister, Depends(get_model_lister)]
