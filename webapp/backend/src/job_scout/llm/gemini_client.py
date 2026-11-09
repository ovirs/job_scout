"""What the Gemini adapter and its model listing share about connecting to Google."""

import httpx2
from google.genai import types

# The SDK waits for ever by default; ten minutes, as the Anthropic SDK waits
TIMEOUT_MS = 10 * 60 * 1000

# The SDK reports a request that never got an answer (a timeout, a dropped connection) as
# its HTTP client's own error, `httpx2`'s
TRANSPORT_ERRORS = (httpx2.HTTPError,)


def http_options(http: httpx2.AsyncClient | None) -> types.HttpOptions:
    """The SDK's HTTP options, on `http` in place of its own client when given (in tests).
    The SDK never retries: the run's queue does."""
    return types.HttpOptions(timeout=TIMEOUT_MS, httpx_async_client=http)
