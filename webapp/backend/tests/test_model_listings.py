"""Each Provider's model listing, filtered to the text models the app can use: tested over
listings saved in the shape each Provider's API returns them."""

import json
from pathlib import Path
from typing import Any

from anthropic.types import ModelInfo

from job_scout.llm import anthropic_models, gemini_models, openai_models
from job_scout.llm.interface import ListedModel

LISTINGS = Path(__file__).parent / "listings"


def saved_listing(provider: str) -> Any:
    return json.loads((LISTINGS / f"{provider}.json").read_text())


def test_anthropic_keeps_active_models_with_structured_outputs_and_their_effort_levels() -> None:
    listing = [ModelInfo.model_validate(entry) for entry in saved_listing("anthropic")["data"]]

    assert anthropic_models.text_models(listing) == [
        ListedModel(
            provider="anthropic",
            id="claude-opus-5-5",
            display_name="Claude Opus 5.5",
            snapshot=False,
            efforts=("low", "medium", "high", "xhigh", "max"),
        ),
        ListedModel(
            provider="anthropic",
            id="claude-sonnet-5",
            display_name="Claude Sonnet 5",
            snapshot=False,
            efforts=("low", "medium", "high"),
        ),
        ListedModel(
            provider="anthropic",
            id="claude-haiku-4-5-20251001",
            display_name="Claude Haiku 4.5",
            snapshot=True,
            efforts=(),
        ),
    ]


def test_openai_keeps_chat_families_and_flags_dated_snapshots() -> None:
    ids = [entry["id"] for entry in saved_listing("openai")["data"]]

    kept = openai_models.text_models(ids)

    assert [(model.id, model.snapshot) for model in kept] == [
        ("gpt-5.1", False),
        ("gpt-5.1-2025-11-13", True),
        ("gpt-5", False),
        ("gpt-5-2025-08-07", True),
        ("gpt-5-mini", False),
        ("gpt-4.1", False),
        ("o3", False),
        ("o4-mini-2025-04-16", True),
    ]
    assert {model.display_name for model in kept if model.id == "gpt-5"} == {"gpt-5"}
    assert {model.efforts for model in kept} == {
        ("none", "minimal", "low", "medium", "high", "xhigh")
    }


def test_gemini_keeps_text_models_that_generate_content_and_flags_dated_or_versioned_names() -> (
    None
):
    listing = [
        gemini_models.GeminiModel(
            name=entry["name"],
            display_name=entry["displayName"],
            generation_methods=tuple(entry["supportedGenerationMethods"]),
            thinking=entry.get("thinking", False),
        )
        for entry in saved_listing("google")["models"]
    ]

    kept = gemini_models.text_models(listing)

    assert [(model.id, model.display_name, model.snapshot) for model in kept] == [
        ("gemini-3-pro-preview", "Gemini 3 Pro Preview", False),
        ("gemini-2.5-pro", "Gemini 2.5 Pro", False),
        ("gemini-flash-latest", "Gemini Flash Latest", False),
        ("gemini-2.5-flash-preview-09-2025", "Gemini 2.5 Flash Preview Sep 2025", True),
        ("gemini-2.5-flash-lite-preview-06-17", "Gemini 2.5 Flash-Lite Preview 06-17", True),
        ("gemini-2.0-flash-001", "Gemini 2.0 Flash 001", True),
        ("gemini-2.0-flash", "Gemini 2.0 Flash", False),
    ]
    efforts = {model.id: model.efforts for model in kept}
    assert efforts["gemini-3-pro-preview"] == ("minimal", "low", "medium", "high")
    assert efforts["gemini-2.0-flash"] == ()
