"""Each step's schema in OpenAI's strict structured-output dialect: every object closed to
other properties, every property required, and any keyword outside OpenAI's subset refused
rather than dropped."""

from typing import Annotated

import pytest
from pydantic import BaseModel, Field

from job_scout.clippings.extraction import ManualEntryExtraction
from job_scout.cover_letters.prompt import CoverLetterResult
from job_scout.evaluations.prompt import EvaluationResult
from job_scout.llm import openai_schema


class Technology(BaseModel):
    name: str


class Posting(BaseModel):
    """A posting."""

    required: list[Technology]
    salary: float | None


def test_every_object_is_closed_and_references_are_kept() -> None:
    assert openai_schema.convert(Posting) == {
        "$defs": {
            "Technology": {
                "additionalProperties": False,
                "properties": {"name": {"title": "Name", "type": "string"}},
                "required": ["name"],
                "title": "Technology",
                "type": "object",
            }
        },
        "additionalProperties": False,
        "description": "A posting.",
        "properties": {
            "required": {
                "items": {"$ref": "#/$defs/Technology"},
                "title": "Required",
                "type": "array",
            },
            "salary": {"anyOf": [{"type": "number"}, {"type": "null"}], "title": "Salary"},
        },
        "required": ["required", "salary"],
        "title": "Posting",
        "type": "object",
    }


@pytest.mark.parametrize("schema", [ManualEntryExtraction, EvaluationResult, CoverLetterResult])
def test_every_step_schema_converts(schema: type[BaseModel]) -> None:
    converted = openai_schema.convert(schema)

    assert converted["additionalProperties"] is False
    assert converted["required"] == list(converted["properties"])


class Open(BaseModel):
    tags: dict[str, str]


def test_an_object_open_to_other_properties_is_refused() -> None:
    with pytest.raises(openai_schema.UnsupportedSchema, match="additionalProperties"):
        openai_schema.convert(Open)


class Noted(BaseModel):
    note: str | None = None


def test_an_optional_nullable_property_is_required_without_its_default() -> None:
    assert openai_schema.convert(Noted)["properties"] == {
        "note": {"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Note"}
    }
    assert openai_schema.convert(Noted)["required"] == ["note"]


class Counted(BaseModel):
    count: int = 3


def test_an_optional_property_that_is_not_nullable_is_refused() -> None:
    with pytest.raises(openai_schema.UnsupportedSchema, match="count"):
        openai_schema.convert(Counted)


class Coded(BaseModel):
    code: Annotated[str, Field(min_length=3)]


def test_a_keyword_outside_openais_subset_is_refused() -> None:
    with pytest.raises(openai_schema.UnsupportedSchema, match="minLength"):
        openai_schema.convert(Coded)


class Described(BaseModel):
    technology: Annotated[Technology, Field(description="The main one")]


def test_a_reference_with_keywords_beside_it_is_refused() -> None:
    with pytest.raises(openai_schema.UnsupportedSchema, match="beside"):
        openai_schema.convert(Described)
