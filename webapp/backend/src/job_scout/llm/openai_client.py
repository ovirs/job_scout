"""What the OpenAI adapter and its model listing share about connecting to OpenAI."""

import httpx2
import openai


def client(api_key: str, http: httpx2.AsyncClient | None) -> openai.AsyncOpenAI:
    """A client on `http` in place of its own when given (in tests). It waits ten minutes,
    the SDK's default, and never retries: the run's queue does."""
    return openai.AsyncOpenAI(api_key=api_key, max_retries=0, http_client=http)


def message(error: openai.APIError) -> str:
    """OpenAI's own words for the error, from its body when it has one."""
    if isinstance(error.body, dict):
        found = error.body.get("message")
        if isinstance(found, str):
            return found
    return str(error)
