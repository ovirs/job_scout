"""Finding a quote the LLM took from a Job Posting, so an invented one can be rejected.

A quote matches when it occurs in one of the posting's fields once both are
normalised: whitespace collapsed, case ignored, curly and straight quotes the
same, and bullet characters dropped. A quote may also start with the label the
prompt gives a field (`Location: New York, NY`); it then matches when the rest is
in that same field. The match is reported as a position in the field's original
text, so the posting view can highlight it.
"""

from typing import Literal

from pydantic import BaseModel

from job_scout.evaluation import POSTING_LABELS, PostingText

PostingField = Literal["description", "title", "location_text", "company"]

SINGLE_QUOTES = "‘’‚‛′`´"
DOUBLE_QUOTES = "“”„‟″«»"
BULLETS = "•◦▪▫‣●○■□►▸▹➢➤✓✔·"
LINE_BULLETS = "-*+"  # bullets only at the start of a line, before whitespace


class EvidenceMatch(BaseModel):
    field: PostingField
    start: int  # in the field's text as stored
    end: int  # exclusive


def find(quote: str, posting: PostingText) -> EvidenceMatch | None:
    """Where the quote occurs in the posting, the description searched first."""
    needle, _ = _normalise(quote)
    if not needle:
        return None
    fields: list[tuple[PostingField, str | None]] = [
        ("description", posting.description),
        ("title", posting.title),
        ("location_text", posting.location_text),
        ("company", posting.company),
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
    label, _ = _normalise(POSTING_LABELS[field])
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
