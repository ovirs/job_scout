"""Each step's schema in Gemini's structured-output dialect: references written out in
place, and any keyword outside Gemini's subset refused rather than dropped."""

from typing import Annotated, Self

import pytest
from pydantic import BaseModel, Field

from job_scout.clippings.extraction import ManualEntryExtraction
from job_scout.cover_letters.prompt import CoverLetterResult
from job_scout.evaluations.prompt import EvaluationResult
from job_scout.llm import gemini_schema


class Technology(BaseModel):
    name: str


class Posting(BaseModel):
    """A posting."""

    required: list[Technology]
    salary: float | None


def test_references_are_written_out_where_they_are_used() -> None:
    assert gemini_schema.convert(Posting) == {
        "description": "A posting.",
        "properties": {
            "required": {
                "items": {
                    "properties": {"name": {"title": "Name", "type": "string"}},
                    "required": ["name"],
                    "title": "Technology",
                    "type": "object",
                },
                "title": "Required",
                "type": "array",
            },
            "salary": {"anyOf": [{"type": "number"}, {"type": "null"}], "title": "Salary"},
        },
        "required": ["required", "salary"],
        "title": "Posting",
        "type": "object",
    }


def test_the_cover_letter_schema_converts_as_it_is() -> None:
    assert gemini_schema.convert(CoverLetterResult) == {
        "description": "The LLM's answer.",
        "properties": {
            "letter": {"title": "Letter", "type": "string"},
            "unsupported_requirements": {
                "items": {"type": "string"},
                "title": "Unsupported Requirements",
                "type": "array",
            },
        },
        "required": ["letter", "unsupported_requirements"],
        "title": "CoverLetterResult",
        "type": "object",
    }


@pytest.mark.parametrize("schema", [ManualEntryExtraction, EvaluationResult])
def test_every_step_schema_converts_with_no_reference_left(schema: type[BaseModel]) -> None:
    converted = repr(gemini_schema.convert(schema))

    assert "$ref" not in converted
    assert "$defs" not in converted


class Coded(BaseModel):
    code: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


def test_a_keyword_outside_geminis_subset_is_refused() -> None:
    with pytest.raises(gemini_schema.UnsupportedSchema, match="pattern"):
        gemini_schema.convert(Coded)


class Node(BaseModel):
    children: list[Self]


def test_a_recursive_schema_is_refused() -> None:
    with pytest.raises(gemini_schema.UnsupportedSchema, match="Node"):
        gemini_schema.convert(Node)
