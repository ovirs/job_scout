"""OpenAI's model listing, filtered by name: its listing reports no capabilities, only ids.

The chat families are kept, minus names that mark another kind of model, and fine-tunes.
The rules match the shape of names, never a list of models, so new models pass through;
re-check them when OpenAI's catalogue changes shape. OpenAI has no adapter yet (#57), so
nothing lists its models: its adapter will call the listing and pass the ids here.
"""

import re
from collections.abc import Iterable

from job_scout.llm.interface import ListedModel

# The chat families: `gpt-5`, `gpt-4.1`, `o3`, `o4-mini`
CHAT_FAMILY = re.compile(r"^(gpt-|o\d)")

# Parts of a name that mark a model for speech, audio, images, video, search, embeddings
# or moderation
OTHER_KINDS = (
    "-tts",
    "-transcribe",
    "-audio",
    "-realtime",
    "-image",
    "-search",
    "embedding",
    "moderation",
    "whisper",
    "dall-e",
    "sora",
)

FINE_TUNE = "ft:"

# A name pinned to one release ends in its date, as in `gpt-5-2025-08-07`
DATED = re.compile(r"-\d{4}-\d{2}-\d{2}$")

# Every level `reasoning.effort` takes; the listing does not say which a model accepts
EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh")


def text_models(ids: Iterable[str]) -> list[ListedModel]:
    """The models among the listed ids the app can use, in the listing's order."""
    return [
        ListedModel(
            provider="openai",
            id=model_id,
            display_name=model_id,
            snapshot=DATED.search(model_id) is not None,
            efforts=EFFORTS,
        )
        for model_id in ids
        if CHAT_FAMILY.match(model_id)
        and not model_id.startswith(FINE_TUNE)
        and not any(kind in model_id for kind in OTHER_KINDS)
    ]
