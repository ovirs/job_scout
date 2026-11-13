"""Each Provider's adapter and model listing, in one map: what the worker connects to for a
run, what the API checks a key with, and so which Providers are available at all.

Adding a Provider (ADR-0005) means writing its adapter and adding it to `ADAPTERS`.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from job_scout.llm import (
    anthropic_adapter,
    anthropic_models,
    gemini_adapter,
    gemini_models,
    openai_adapter,
    openai_models,
)
from job_scout.llm.interface import Connect, KeyRefused, ListedModel, Llm, ModelChoice, Provider


@dataclass(frozen=True)
class Adapter:
    """One Provider's adapter, on its official SDK."""

    llm: Connect  # an `Llm` calling a model choice with a key, for the run's owner
    # The models it lists for a key that the app can use, filtered by its own rules
    list_models: Callable[[str], Awaitable[list[ListedModel] | KeyRefused]]


# A Provider is available, and can be set up, once it is here
ADAPTERS: dict[Provider, Adapter] = {
    "anthropic": Adapter(anthropic_adapter.AnthropicLlm, anthropic_models.list_models),
    "openai": Adapter(openai_adapter.OpenAiLlm, openai_models.list_models),
    "google": Adapter(gemini_adapter.GeminiLlm, gemini_models.list_models),
}


def connect(choice: ModelChoice, api_key: str, owner_id: uuid.UUID) -> Llm:
    """Connects to the adapter of the choice's Provider with a key, for one attempt of a
    run of the owner's."""
    return ADAPTERS[choice.provider].llm(choice, api_key, owner_id)


class ProviderModelLister:
    """Lists an available Provider's models with its official SDK."""

    available: tuple[Provider, ...] = tuple(ADAPTERS)

    async def list_models(self, provider: Provider, api_key: str) -> list[ListedModel] | KeyRefused:
        return await ADAPTERS[provider].list_models(api_key)
