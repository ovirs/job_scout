"""A step's schema in Gemini's structured-output dialect, for `response_json_schema`.

Gemini takes a subset of JSON Schema. Its docs show `$ref` only for a schema referring to
itself, so every reference is written out in place, and a recursive schema is refused.
A keyword outside the subset is refused too, never dropped: the answer is checked against
the step's own schema in code either way, but a dropped keyword would leave Gemini
producing answers that check would refuse. The step schemas use only the subset.
"""

from typing import Any

from pydantic import BaseModel

# The keywords Gemini enforces, as its structured-output docs list them
SUPPORTED = frozenset(
    {
        "type",
        "title",
        "description",
        "properties",
        "required",
        "additionalProperties",
        "enum",
        "format",
        "minimum",
        "maximum",
        "items",
        "prefixItems",
        "minItems",
        "maxItems",
        "anyOf",
    }
)

DEFS_PREFIX = "#/$defs/"


class UnsupportedSchema(Exception):
    """The schema uses something Gemini's dialect cannot express."""


def convert(schema: type[BaseModel]) -> dict[str, Any]:
    """The schema of `schema` in Gemini's dialect. Raises `UnsupportedSchema`."""
    full = schema.model_json_schema()
    defs: dict[str, Any] = full.pop("$defs", {})
    converted: dict[str, Any] = _convert(full, defs, resolving=())
    return converted


def _convert(node: Any, defs: dict[str, Any], resolving: tuple[str, ...]) -> Any:
    if isinstance(node, list):
        return [_convert(item, defs, resolving) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        name = _definition(node["$ref"])
        if name in resolving:
            raise UnsupportedSchema(f"{name} refers to itself, which Gemini cannot take")
        siblings = {key: value for key, value in node.items() if key != "$ref"}
        return _convert({**defs[name], **siblings}, defs, (*resolving, name))
    converted: dict[str, Any] = {}
    for keyword, value in node.items():
        if keyword not in SUPPORTED:
            raise UnsupportedSchema(f"Gemini does not take the keyword {keyword!r}")
        if keyword == "properties":
            # The keys are property names, not keywords
            converted[keyword] = {
                name: _convert(sub, defs, resolving) for name, sub in value.items()
            }
        elif keyword in ("enum", "required"):
            converted[keyword] = value
        else:
            converted[keyword] = _convert(value, defs, resolving)
    return converted


def _definition(ref: str) -> str:
    if not ref.startswith(DEFS_PREFIX):
        raise UnsupportedSchema(f"Gemini cannot follow the reference {ref!r}")
    return ref.removeprefix(DEFS_PREFIX)
