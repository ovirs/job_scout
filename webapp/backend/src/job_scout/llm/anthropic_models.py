"""Anthropic's model listing, filtered by the capabilities each model reports: the active
models that support structured outputs, with the effort levels they accept.

The listing call is not covered by automated tests; the filtering is.
"""

import re
from collections.abc import Iterable

import anthropic
from anthropic.types import ModelInfo
from anthropic.types.effort_capability import EffortCapability

from job_scout.llm.interface import KeyRefused, ListedModel

# A name pinned to one release ends in its date, as in `claude-haiku-4-5-20251001`
DATED = re.compile(r"-\d{8}$")


def text_models(listing: Iterable[ModelInfo]) -> list[ListedModel]:
    """The models in the listing the app can use, in the listing's order."""
    return [
        ListedModel(
            provider="anthropic",
            id=model.id,
            display_name=model.display_name,
            snapshot=DATED.search(model.id) is not None,
            efforts=efforts(model.capabilities.effort),
        )
        for model in listing
        if model.lifecycle == "active"
        and model.capabilities is not None
        and model.capabilities.structured_outputs.supported
    ]


def efforts(effort: EffortCapability) -> tuple[str, ...]:
    """The effort levels the model accepts, from the lowest."""
    if not effort.supported:
        return ()
    levels = {
        "low": effort.low,
        "medium": effort.medium,
        "high": effort.high,
        "xhigh": effort.xhigh,
        "max": effort.max,
    }
    return tuple(level for level, support in levels.items() if support and support.supported)


async def list_models(api_key: str) -> list[ListedModel] | KeyRefused:
    """The models Anthropic lists for the key that the app can use; or why the listing
    failed."""
    try:
        async with anthropic.AsyncAnthropic(api_key=api_key) as client:
            listing = [model async for model in client.models.list()]
    except anthropic.APIError as error:
        return KeyRefused(str(error))
    return text_models(listing)
