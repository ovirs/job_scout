"""The facts the LLM extracts from a Job Posting, stored as its second layer.

They are facts for display (and later filtering) and are never inputs to the
Evaluation (ADR 0003).
"""

from typing import Literal

from pydantic import BaseModel

WorkplaceType = Literal["remote", "hybrid", "onsite"]


class SalaryRange(BaseModel):
    minimum: float | None
    maximum: float | None
    currency: str  # ISO 4217
    period: Literal["year", "month", "day", "hour"]
    applies_to: str | None  # "New York and San Francisco", "EU", ...


class Technology(BaseModel):
    name: str
    alternative_group: int | None  # same number = "any one of these"


class ExtractedFields(BaseModel):
    salary_ranges: list[SalaryRange]
    seniority: list[
        Literal[
            "intern",
            "junior",
            "mid",
            "senior",
            "staff",
            "principal",
            "lead",
            "manager",
            "director",
            "executive",
        ]
    ]
    employment_type: Literal["full_time", "part_time", "contract", "internship", "temporary"] | None
    workplace_type: WorkplaceType | None
    location_restriction: str | None
    required_technologies: list[Technology]
    nice_to_have_technologies: list[Technology]
