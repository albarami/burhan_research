"""Schema-walking case generator for the conformance harness (Fix 4b).

Walks each governed schema alongside a known-valid base instance and emits:

- **mutants** — for every assertive-keyword instance reachable in the base
  instance, a copy violating exactly that keyword at that JSON path (must be
  rejected by the governed schema, and the model must agree);
- **variants** — boundary-valid copies (enum members, exact bounds, minimal
  arrays, extra keys where ``additionalProperties`` permits them) on which the
  two validators must also agree;
- **format probes** — ``format`` is annotation-only under the locked
  jsonschema install (Hypothesis H2), so those sites assert the expected
  asymmetry: schema accepts, model (real datetime/date types) rejects.

Keyword coverage is self-policing: ``assertive_keywords_used`` reports every
assertive keyword occurring in a schema, and the meta-test requires ≥1
generated mutant per (schema, keyword) — an unreachable subtree or a new
keyword fails the suite instead of going silently untested.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

# Keywords the generator produces violating mutants for.
HANDLED_KEYWORDS = frozenset(
    {
        "type",
        "enum",
        "const",
        "pattern",
        "required",
        "additionalProperties",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minItems",
        "if",
        "then",
    }
)

# Structural keywords the walker traverses rather than mutates.
STRUCTURAL_KEYWORDS = frozenset({"properties", "items", "allOf", "$ref", "$defs"})

# Non-assertive keywords under the locked validator setup. ``format`` is
# asymmetry-probed (H2); ``default`` is covered by the default-agreement test.
ANNOTATION_KEYWORDS = frozenset({"$schema", "$id", "title", "description", "format", "default"})

Path = list[str | int]


@dataclass
class Case:
    """One generated conformance case."""

    schema_name: str
    kind: str  # "mutant" | "variant" | "format_probe"
    keyword: str
    path: str
    instance: Any


@dataclass
class _Walk:
    schema_name: str
    root_schema: dict[str, Any]
    base: Any
    cases: list[Case] = field(default_factory=list)


def _resolve(schema: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in schema:
        pointer = schema["$ref"]
        if not pointer.startswith("#/"):
            raise AssertionError(f"non-local $ref not supported: {pointer}")
        node: Any = root
        for part in pointer[2:].split("/"):
            node = node[part]
        schema = node
    return schema


def _mutated(base: Any, path: Path, value: Any) -> Any:
    clone = copy.deepcopy(base)
    if not path:
        return value
    node = clone
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return clone


def _deleted(base: Any, path: Path, key: str) -> Any:
    clone = copy.deepcopy(base)
    node = clone
    for part in path:
        node = node[part]
    del node[key]
    return clone


def _fmt(path: Path) -> str:
    out = "$"
    for part in path:
        out += f"[{part}]" if isinstance(part, int) else f".{part}"
    return out


def _add(walk: _Walk, kind: str, keyword: str, path: Path, instance: Any) -> None:
    walk.cases.append(Case(walk.schema_name, kind, keyword, _fmt(path), instance))


def _wrong_value(declared: str | list[str]) -> Any:
    types = [declared] if isinstance(declared, str) else list(declared)
    if "array" not in types:
        return [1]
    if "object" not in types:
        return {"__wrong__": True}
    return "unreachable-wrong-type"


def _type_cases(walk: _Walk, sch: dict[str, Any], path: Path) -> None:
    declared = sch.get("type")
    if declared is not None:
        _add(walk, "mutant", "type", path, _mutated(walk.base, path, _wrong_value(declared)))


def _scalar_cases(walk: _Walk, sch: dict[str, Any], path: Path) -> None:
    if "enum" in sch:
        _add(walk, "mutant", "enum", path, _mutated(walk.base, path, "___not_in_enum___"))
        for member in sch["enum"]:
            _add(walk, "variant", "enum", path, _mutated(walk.base, path, member))
    if "const" in sch:
        _add(walk, "mutant", "const", path, _mutated(walk.base, path, "___not_const___"))
        _add(walk, "variant", "const", path, _mutated(walk.base, path, sch["const"]))
    if "pattern" in sch:
        _add(walk, "mutant", "pattern", path, _mutated(walk.base, path, "###no-match###"))
    if "minimum" in sch:
        bound = sch["minimum"]
        _add(walk, "mutant", "minimum", path, _mutated(walk.base, path, bound - 1))
        _add(walk, "variant", "minimum", path, _mutated(walk.base, path, bound))
    if "maximum" in sch:
        bound = sch["maximum"]
        _add(walk, "mutant", "maximum", path, _mutated(walk.base, path, bound + 1))
        _add(walk, "variant", "maximum", path, _mutated(walk.base, path, bound))
    if "exclusiveMinimum" in sch:
        bound = sch["exclusiveMinimum"]
        _add(walk, "mutant", "exclusiveMinimum", path, _mutated(walk.base, path, bound))
        _add(
            walk,
            "variant",
            "exclusiveMinimum",
            path,
            _mutated(walk.base, path, bound + 0.000001),
        )
    if "exclusiveMaximum" in sch:
        bound = sch["exclusiveMaximum"]
        _add(walk, "mutant", "exclusiveMaximum", path, _mutated(walk.base, path, bound))
        _add(
            walk,
            "variant",
            "exclusiveMaximum",
            path,
            _mutated(walk.base, path, bound - 0.000001),
        )
    if sch.get("format") in {"date-time", "date"}:
        _add(
            walk,
            "format_probe",
            "format",
            path,
            _mutated(walk.base, path, "not-a-valid-datetime"),
        )


def _object_cases(walk: _Walk, sch: dict[str, Any], node: dict[str, Any], path: Path) -> None:
    for required_key in sch.get("required", []):
        if required_key in node:
            _add(
                walk,
                "mutant",
                "required",
                path,
                _deleted(walk.base, path, required_key),
            )
    additional = sch.get("additionalProperties")
    if additional is False:
        _add(
            walk,
            "mutant",
            "additionalProperties",
            path,
            _mutated(walk.base, [*path, "___smuggled___"], 1),
        )
    elif isinstance(additional, dict):
        wrong = _wrong_value(additional.get("type", "string"))
        _add(
            walk,
            "mutant",
            "additionalProperties",
            path,
            _mutated(walk.base, [*path, "___extra___"], wrong),
        )
        _add(
            walk,
            "variant",
            "additionalProperties",
            path,
            _mutated(walk.base, [*path, "___extra___"], "a-string"),
        )
    elif additional is True:
        _add(
            walk,
            "variant",
            "additionalProperties",
            path,
            _mutated(walk.base, [*path, "___extra___"], {"nested": [1, "a", None]}),
        )
    for branch in sch.get("allOf", []):
        condition = branch.get("if")
        consequence = branch.get("then")
        if not condition or not consequence:
            continue
        cond_props = condition.get("properties", {})
        matches = all(
            key in node and node[key] == spec.get("const") for key, spec in cond_props.items()
        )
        if matches:
            for required_key in consequence.get("required", []):
                if required_key in node:
                    _add(
                        walk,
                        "mutant",
                        "if",
                        path,
                        _deleted(walk.base, path, required_key),
                    )
                    _add(
                        walk,
                        "mutant",
                        "then",
                        path,
                        _deleted(walk.base, path, required_key),
                    )


def _walk(walk: _Walk, schema: dict[str, Any], node: Any, path: Path) -> None:
    sch = _resolve(schema, walk.root_schema)
    _type_cases(walk, sch, path)
    if isinstance(node, dict):
        _object_cases(walk, sch, node, path)
        for key, child in node.items():
            child_schema = sch.get("properties", {}).get(key)
            if child_schema is None:
                additional = sch.get("additionalProperties")
                child_schema = additional if isinstance(additional, dict) else None
            if isinstance(child_schema, dict):
                _walk(walk, child_schema, child, [*path, key])
    elif isinstance(node, list):
        if "minItems" in sch:
            floor = sch["minItems"]
            if len(node) >= floor > 0:
                _add(
                    walk,
                    "mutant",
                    "minItems",
                    path,
                    _mutated(walk.base, path, node[: floor - 1]),
                )
                _add(walk, "variant", "minItems", path, _mutated(walk.base, path, node[:floor]))
        item_schema = sch.get("items")
        if isinstance(item_schema, dict) and node:
            _walk(walk, item_schema, node[0], [*path, 0])
    else:
        _scalar_cases(walk, sch, path)


def generate_cases(schema_name: str, schema: dict[str, Any], base: Any) -> list[Case]:
    """Generate all mutants/variants/format-probes for one schema."""
    walk = _Walk(schema_name=schema_name, root_schema=schema, base=base)
    _walk(walk, schema, base, [])
    return walk.cases


def assertive_keywords_used(schema: Any) -> set[str]:
    """Every assertive (non-structural, non-annotation) keyword in a schema.

    Keys directly under ``properties``/``$defs`` are property/definition
    NAMES, not keywords, and are skipped (their subschemas are visited).
    """
    found: set[str] = set()

    def visit(node: Any, *, in_name_map: bool) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if in_name_map:
                    visit(value, in_name_map=False)
                    continue
                if key in {"properties", "$defs"}:
                    visit(value, in_name_map=True)
                    continue
                if key not in STRUCTURAL_KEYWORDS and key not in ANNOTATION_KEYWORDS:
                    found.add(key)
                visit(value, in_name_map=False)
        elif isinstance(node, list):
            for item in node:
                visit(item, in_name_map=False)

    visit(schema, in_name_map=False)
    return found


def declared_defaults(schema: Any) -> dict[str, Any]:
    """Every ``default`` declared in a schema, keyed by schema-tree pointer."""
    found: dict[str, Any] = {}

    def visit(node: Any, pointer: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "default":
                    found[f"{pointer}.default"] = value
                else:
                    visit(value, f"{pointer}.{key}")
        elif isinstance(node, list):
            for index, item in enumerate(node):
                visit(item, f"{pointer}[{index}]")

    visit(schema, "$")
    return found
