"""Each Provider's adapter and model listing, in one map: what the worker connects to for a
run, what the API checks a key with, and so which Providers are available at all.

Adding a Provider (ADR-0005) means writing its adapter and adding it to `ADAPTERS`.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from job_scout.config import Settings
from job_scout.llm import anthropic_adapter
from job_scout.llm.interface import Connect, KeyRefused, Llm, Provider


@dataclass(frozen=True)
class Adapter:
    """One Provider's adapter, on its official SDK."""

    llm: Callable[[Settings, str], Llm]  # an `Llm` calling the Provider with a key
    list_models: Callable[[str], Awaitable[list[str] | KeyRefused]]


# A Provider is available, and can be set up, once it is here
ADAPTERS: dict[Provider, Adapter] = {
    "anthropic": Adapter(anthropic_adapter.AnthropicLlm, anthropic_adapter.list_models),
}


def connector(settings: Settings) -> Connect:
    """Connects to a Provider's adapter with a key, for one run attempt."""

    def connect(provider: Provider, api_key: str) -> Llm:
        return ADAPTERS[provider].llm(settings, api_key)

    return connect


class ProviderModelLister:
    """Lists an available Provider's models with its official SDK."""

    available: tuple[Provider, ...] = tuple(ADAPTERS)

    async def list_models(self, provider: Provider, api_key: str) -> list[str] | KeyRefused:
        return await ADAPTERS[provider].list_models(api_key)
