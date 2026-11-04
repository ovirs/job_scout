"""The prompts the app sends to the LLM, one file per step.

Each file starts with a header naming its version, which every LLM-produced
record stores. Change a prompt's text and bump its version together.
"""

from dataclasses import dataclass
from importlib.resources import files


@dataclass(frozen=True)
class Prompt:
    version: str
    text: str


def load(name: str) -> Prompt:
    source = (files(__package__) / f"{name}.md").read_text(encoding="utf-8")
    _, header, text = source.split("---\n", 2)
    key, _, version = header.strip().partition(": ")
    if key != "version" or not version:
        raise ValueError(f"Prompt {name!r} must start with a 'version: ...' header")
    return Prompt(version=version, text=text.strip())


def tagged(tag: str, text: str) -> str:
    """A block of a prompt: the text, stripped, between an opening and a closing tag."""
    return f"<{tag}>\n{text.strip()}\n</{tag}>"


MANUAL_ENTRY_EXTRACTION = load("manual-entry-extraction")
EVALUATION = load("evaluation")
COVER_LETTER = load("cover-letter")
