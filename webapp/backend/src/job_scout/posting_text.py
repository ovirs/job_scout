"""A Job Posting as the LLM reads it: the block every prompt sends it in, and the check
that a quote the LLM took from it is really there.

The LLM reads the posting's own text only: title, company, location and description.
Extracted fields never feed a prompt (ADR 0003), nor does the workplace type, which is
one of them. Each field is sent after a label, and the quote check knows those labels,
so the layout and the check cannot disagree.

A quote matches when it occurs in one of the posting's fields once both are
normalised: whitespace collapsed, case ignored, curly and straight quotes the
same, and bullet characters dropped. A quote may also start with the label a field
is rendered with (`Location: New York, NY`); it then matches when the rest is in
that same field. The match is reported as a position in the field's original text,
so the posting view can highlight it.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from job_scout.job_postings.models import JobPosting
from job_scout.prompts import tagged

SINGLE_QUOTES = "‘’‚‛′`´"
DOUBLE_QUOTES = "“”„‟″«»"
BULLETS = "•◦▪▫‣●○■□►▸▹➢➤✓✔·"
LINE_BULLETS = "-*+"  # bullets only at the start of a line, before whitespace

PostingField = Literal["description", "title", "location_text", "company"]

# The label each field gets in the rendered posting. The posting does not contain these
# words, but a model may quote a field with its label, so `find` accepts it.
_LABELS: dict[PostingField, str] = {
    "title": "Title:",
    "company": "Company:",
    "location_text": "Location:",
    "description": "Description:",
}


class EvidenceMatch(BaseModel):
    field: PostingField
    start: int  # in the field's text as stored
    end: int  # exclusive


@dataclass(frozen=True)
class PostingText:
    """The part of a Job Posting the LLM reads, and the text its quotes must come from."""

    title: str
    company: str
    location_text: str | None
    description: str

    @classmethod
    def of(cls, posting: JobPosting) -> "PostingText":
        """The posting's text as it is now."""
        return cls(
            title=posting.title,
            company=posting.company,
            location_text=posting.location_text,
            description=posting.description,
        )

    def render(self) -> str:
        """The posting as a prompt block: each field after its label, the description
        last and on lines of its own; a posting with no location has no location line."""
        lines = [f"{_LABELS['title']} {self.title}", f"{_LABELS['company']} {self.company}"]
        if self.location_text:
            lines.append(f"{_LABELS['location_text']} {self.location_text}")
        lines += [_LABELS["description"], self.description]
        return tagged("job_posting", "\n".join(lines))

    def find(self, quote: str) -> EvidenceMatch | None:
        """Where the quote occurs in the posting, the description searched first."""
        needle, _ = _normalise(quote)
        if not needle:
            return None
        fields: list[tuple[PostingField, str | None]] = [
            ("description", self.description),
            ("title", self.title),
            ("location_text", self.location_text),
            ("company", self.company),
        ]
        for field, text in fields:
            if text is None:
                continue
            haystack, positions = _normalise(text)
            for wanted in [needle, _without_label(needle, field)]:
                if not wanted:
                    continue
                at = haystack.find(wanted)
                if at >= 0:
                    return EvidenceMatch(
                        field=field, start=positions[at], end=positions[at + len(wanted) - 1] + 1
                    )
        return None


def _without_label(needle: str, field: PostingField) -> str | None:
    """The normalised quote after the field's own label, if it starts with that label."""
    label, _ = _normalise(_LABELS[field])
    if not needle.startswith(label):
        return None
    return needle[len(label) :].lstrip(" ") or None


def _normalise(text: str) -> tuple[str, list[int]]:
    """The normalised text, and for each of its characters the index it came from."""
    chars: list[str] = []
    positions: list[int] = []
    at_line_start = True
    for index, char in enumerate(text):
        is_line_bullet = (
            at_line_start
            and char in LINE_BULLETS
            and (index + 1 == len(text) or text[index + 1].isspace())
        )
        if char == "\n":
            at_line_start = True
        elif not char.isspace():
            at_line_start = False
        if char.isspace() or char in BULLETS or is_line_bullet:
            if chars and chars[-1] != " ":
                chars.append(" ")
                positions.append(index)
            continue
        if char in SINGLE_QUOTES:
            char = "'"
        elif char in DOUBLE_QUOTES:
            char = '"'
        for lowered in char.lower():
            chars.append(lowered)
            positions.append(index)
    if chars and chars[-1] == " ":
        chars.pop()
        positions.pop()
    return "".join(chars), positions
