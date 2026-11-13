"""A step's schema in OpenAI's strict structured-output dialect, for `text.format`.

Strict mode takes a subset of JSON Schema in which every object is closed to other
properties (`additionalProperties: false`) and every property is required: an optional one
is sent as required and nullable, its default of null dropped. References to `$defs` are
kept: OpenAI follows them. A keyword outside the subset is refused, never dropped: the
answer is checked against the step's own schema in code either way, but a dropped keyword
would leave OpenAI producing answers that check would refuse. The step schemas use only the
subset.
"""

from typing import Any

from pydantic import BaseModel

# The keywords strict mode takes, as OpenAI's structured-output docs list them
SUPPORTED = frozenset(
    {
        "$defs",
        "$ref",
        "type",
        "title",
        "description",
        "properties",
        "required",
        "additionalProperties",
        "enum",
        "const",
        "anyOf",
        "items",
        "minItems",
        "maxItems",
        "pattern",
        "format",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
    }
)


class UnsupportedSchema(Exception):
    """The schema uses something OpenAI's strict dialect cannot express."""


def convert(schema: type[BaseModel]) -> dict[str, Any]:
    """The schema of `schema` in OpenAI's strict dialect. Raises `UnsupportedSchema`."""
    converted: dict[str, Any] = _convert(schema.model_json_schema())
    return converted


def _convert(node: Any) -> Any:
    if isinstance(node, list):
        return [_convert(item) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node and len(node) > 1:
        others = sorted(key for key in node if key != "$ref")
        raise UnsupportedSchema(f"OpenAI cannot take {others} beside a reference")
    if node.get("type") == "object":
        node = _all_required(node)
    converted: dict[str, Any] = {}
    for keyword, value in node.items():
        if keyword not in SUPPORTED:
            raise UnsupportedSchema(f"OpenAI does not take the keyword {keyword!r}")
        if keyword in ("properties", "$defs"):
            # The keys are names, not keywords
            converted[keyword] = {name: _convert(sub) for name, sub in value.items()}
        elif keyword == "additionalProperties":
            if value is not False:
                raise UnsupportedSchema("OpenAI takes only additionalProperties: false")
            converted[keyword] = value
        elif keyword in ("enum", "const", "required"):
            converted[keyword] = value
        else:
            converted[keyword] = _convert(value)
    if node.get("type") == "object":
        converted["additionalProperties"] = False
    return converted


def _all_required(node: dict[str, Any]) -> dict[str, Any]:
    """The object with every property required: an optional one, which strict mode cannot
    take, is required once it is nullable with no default but null, where null reads as
    the default. Any other optional property is refused."""
    properties: dict[str, Any] = node.get("properties", {})
    required: list[str] = node.get("required", [])
    rewritten = {}
    for name, sub in properties.items():
        if name not in required:
            if not (_nullable(sub) and "default" in sub and sub["default"] is None):
                raise UnsupportedSchema(f"OpenAI needs the optional property {name!r} nullable")
            sub = {key: value for key, value in sub.items() if key != "default"}
        rewritten[name] = sub
    if not properties:
        return node
    return {**node, "properties": rewritten, "required": list(properties)}


def _nullable(node: dict[str, Any]) -> bool:
    return node.get("type") == "null" or any(
        variant.get("type") == "null" for variant in node.get("anyOf", [])
    )
