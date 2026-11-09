"""Gemini's model listing, filtered: the models that support `generateContent`, minus names
that mark another kind of model.

The rules match the shape of names, never a list of models, so new models pass through;
re-check them when Google's catalogue changes shape.
"""

import re
from collections.abc import Iterable

import httpx2
from google import genai
from google.genai import types

from job_scout.llm.gemini_client import TRANSPORT_ERRORS, http_options
from job_scout.llm.interface import KeyRefused, ListedModel

GENERATE_CONTENT = "generateContent"

# Parts of a name that mark a model for speech, images, video, music, live audio or
# embeddings, or a model for robots
OTHER_KINDS = (
    "-tts",
    "-image",
    "-live",
    "-audio",
    "embedding",
    "imagen",
    "veo",
    "lyria",
    "robotics",
)

# A name pinned to one release ends in a version or a date: `-001`, `-06-17`, `-09-2025`.
# `-latest` and plain family names, such as `gemini-2.5-pro`, are moving names
PINNED = re.compile(r"-(\d{3}|\d{2}-\d{2}|\d{2}-\d{4}|\d{4}-\d{2}-\d{2})$")

# Every level `thinkingConfig.thinkingLevel` takes; the listing says only whether a model
# thinks
EFFORTS = ("minimal", "low", "medium", "high")

PREFIX = "models/"


def text_models(listing: Iterable[types.Model]) -> list[ListedModel]:
    """The models in the listing the app can use, in the listing's order. The SDK names
    the listing's `supportedGenerationMethods` `supported_actions`."""
    kept = []
    for model in listing:
        model_id = (model.name or "").removeprefix(PREFIX)
        if GENERATE_CONTENT not in (model.supported_actions or ()) or any(
            kind in model_id for kind in OTHER_KINDS
        ):
            continue
        kept.append(
            ListedModel(
                provider="google",
                id=model_id,
                display_name=model.display_name or model_id,
                snapshot=PINNED.search(model_id) is not None,
                efforts=EFFORTS if model.thinking else (),
            )
        )
    return kept


async def list_models(
    api_key: str, http: httpx2.AsyncClient | None = None
) -> list[ListedModel] | KeyRefused:
    """The models Gemini lists for the key that the app can use; or why the listing failed.
    `http` replaces the SDK's own HTTP client, as in tests."""
    try:
        async with genai.Client(api_key=api_key, http_options=http_options(http)).aio as client:
            listing = [model async for model in await client.models.list()]
    except genai.errors.APIError as error:
        return KeyRefused(error.message or str(error))
    except TRANSPORT_ERRORS as error:
        return KeyRefused(f"Google could not be reached: {error}")
    return text_models(listing)
