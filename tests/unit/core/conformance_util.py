"""Schema-walking case generator for the conformance harness (Fix 4b + REJECT fix 3).

Walks each governed schema alongside a known-valid base instance and emits:

- **mutants** — for every assertive-keyword occurrence reachable in the base
  instance, a copy violating exactly that keyword at that JSON path (must be
  rejected by the governed schema, and the model must agree);
- **variants** — boundary-valid copies (enum members, exact bounds, minimal
  arrays, extra keys where ``additionalProperties`` permits them) on which the
  two validators must also agree;
- **format probes** — ``format`` is annotation-only under the locked
  jsonschema install (Hypothesis H2), so those sites assert the expected
  asymmetry: schema accepts, model (real datetime/date types) rejects.

Coverage is tracked per keyword **occurrence** — the keyword's pointer in the
schema document (``$.properties.seq.minimum``; ``$ref`` targets resolve to
their ``$defs`` location). Every case records the ``schema_pointer`` of the
occurrence it violates, and the meta-test requires ≥1 mutant per
``(schema_pointer, keyword)`` occurrence, so an optional branch unreachable
from the base instance — or a new keyword — fails the suite instead of going
silently untested. Arrays are walked at EVERY element so heterogeneous items
(e.g. first- and second-order constructs) each reach their conditional
branches.

``if`` interiors are predicates (they select, they do not assert) and are
excluded from the occurrence set; the assertive content of a conditional is
its ``then`` interior (e.g. ``...allOf[0].then.required``), which the walker
violates by deleting the conditionally-required key wherever the condition
matches.
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
    }
)

# Structural/composition keywords the walker traverses rather than mutates.
# ``if``/``then`` are composition: their assertive interiors carry the
# occurrences (see module docstring).
STRUCTURAL_KEYWORDS = frozenset({"properties", "items", "allOf", "$ref", "$defs", "if", "then"})

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
    path: str  # instance JSON path of the mutation site
    schema_pointer: str  # schema-document pointer of the keyword occurrence
    instance: Any


@dataclass
class _Walk:
    schema_name: str
    root_schema: dict[str, Any]
    base: Any
    cases: list[Case] = field(default_factory=list)


def _resolve(
    schema: dict[str, Any], root: dict[str, Any], pointer: str
) -> tuple[dict[str, Any], str]:
    while "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/"):
            raise AssertionError(f"non-local $ref not supported: {ref}")
        node: Any = root
        for part in ref[2:].split("/"):
            node = node[part]
        schema = node
        pointer = "$." + ".".join(ref[2:].split("/"))
    return schema, pointer


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


def _add(
    walk: _Walk, kind: str, keyword: str, path: Path, schema_pointer: str, instance: Any
) -> None:
    walk.cases.append(Case(walk.schema_name, kind, keyword, _fmt(path), schema_pointer, instance))


def _wrong_value(declared: str | list[str]) -> Any:
    types = [declared] if isinstance(declared, str) else list(declared)
    if "array" not in types:
        return [1]
    if "object" not in types:
        return {"__wrong__": True}
    return "unreachable-wrong-type"


def _type_cases(walk: _Walk, sch: dict[str, Any], path: Path, sp: str) -> None:
    declared = sch.get("type")
    if declared is not None:
        _add(
            walk,
            "mutant",
            "type",
            path,
            f"{sp}.type",
            _mutated(walk.base, path, _wrong_value(declared)),
        )


def _scalar_cases(walk: _Walk, sch: dict[str, Any], path: Path, sp: str) -> None:
    if "enum" in sch:
        pointer = f"{sp}.enum"
        _add(walk, "mutant", "enum", path, pointer, _mutated(walk.base, path, "___not_in_enum___"))
        for member in sch["enum"]:
            _add(walk, "variant", "enum", path, pointer, _mutated(walk.base, path, member))
    if "const" in sch:
        pointer = f"{sp}.const"
        _add(walk, "mutant", "const", path, pointer, _mutated(walk.base, path, "___not_const___"))
        _add(walk, "variant", "const", path, pointer, _mutated(walk.base, path, sch["const"]))
    if "pattern" in sch:
        _add(
            walk,
            "mutant",
            "pattern",
            path,
            f"{sp}.pattern",
            _mutated(walk.base, path, "###no-match###"),
        )
    if "minimum" in sch:
        bound = sch["minimum"]
        pointer = f"{sp}.minimum"
        _add(walk, "mutant", "minimum", path, pointer, _mutated(walk.base, path, bound - 1))
        _add(walk, "variant", "minimum", path, pointer, _mutated(walk.base, path, bound))
    if "maximum" in sch:
        bound = sch["maximum"]
        pointer = f"{sp}.maximum"
        _add(walk, "mutant", "maximum", path, pointer, _mutated(walk.base, path, bound + 1))
        _add(walk, "variant", "maximum", path, pointer, _mutated(walk.base, path, bound))
    if "exclusiveMinimum" in sch:
        bound = sch["exclusiveMinimum"]
        pointer = f"{sp}.exclusiveMinimum"
        _add(walk, "mutant", "exclusiveMinimum", path, pointer, _mutated(walk.base, path, bound))
        _add(
            walk,
            "variant",
            "exclusiveMinimum",
            path,
            pointer,
            _mutated(walk.base, path, bound + 0.000001),
        )
    if "exclusiveMaximum" in sch:
        bound = sch["exclusiveMaximum"]
        pointer = f"{sp}.exclusiveMaximum"
        _add(walk, "mutant", "exclusiveMaximum", path, pointer, _mutated(walk.base, path, bound))
        _add(
            walk,
            "variant",
            "exclusiveMaximum",
            path,
            pointer,
            _mutated(walk.base, path, bound - 0.000001),
        )
    if sch.get("format") in {"date-time", "date"}:
        _add(
            walk,
            "format_probe",
            "format",
            path,
            f"{sp}.format",
            _mutated(walk.base, path, "not-a-valid-datetime"),
        )


def _object_cases(
    walk: _Walk, sch: dict[str, Any], node: dict[str, Any], path: Path, sp: str
) -> None:
    for required_key in sch.get("required", []):
        if required_key in node:
            _add(
                walk,
                "mutant",
                "required",
                path,
                f"{sp}.required",
                _deleted(walk.base, path, required_key),
            )
    additional = sch.get("additionalProperties")
    pointer = f"{sp}.additionalProperties"
    if additional is False:
        _add(
            walk,
            "mutant",
            "additionalProperties",
            path,
            pointer,
            _mutated(walk.base, [*path, "___smuggled___"], 1),
        )
    elif isinstance(additional, dict):
        wrong = _wrong_value(additional.get("type", "string"))
        _add(
            walk,
            "mutant",
            "additionalProperties",
            path,
            pointer,
            _mutated(walk.base, [*path, "___extra___"], wrong),
        )
        _add(
            walk,
            "variant",
            "additionalProperties",
            path,
            pointer,
            _mutated(walk.base, [*path, "___extra___"], "a-string"),
        )
    elif additional is True:
        _add(
            walk,
            "variant",
            "additionalProperties",
            path,
            pointer,
            _mutated(walk.base, [*path, "___extra___"], {"nested": [1, "a", None]}),
        )
    for index, branch in enumerate(sch.get("allOf", [])):
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
                        "required",
                        path,
                        f"{sp}.allOf[{index}].then.required",
                        _deleted(walk.base, path, required_key),
                    )


def _walk(walk: _Walk, schema: dict[str, Any], node: Any, path: Path, pointer: str) -> None:
    sch, sp = _resolve(schema, walk.root_schema, pointer)
    _type_cases(walk, sch, path, sp)
    if isinstance(node, dict):
        _object_cases(walk, sch, node, path, sp)
        for key, child in node.items():
            child_schema = sch.get("properties", {}).get(key)
            child_pointer = f"{sp}.properties.{key}"
            if child_schema is None:
                additional = sch.get("additionalProperties")
                if isinstance(additional, dict):
                    child_schema = additional
                    child_pointer = f"{sp}.additionalProperties"
                else:
                    child_schema = None
            if isinstance(child_schema, dict):
                _walk(walk, child_schema, child, [*path, key], child_pointer)
    elif isinstance(node, list):
        if "minItems" in sch:
            floor = sch["minItems"]
            occurrence = f"{sp}.minItems"
            if len(node) >= floor > 0:
                _add(
                    walk,
                    "mutant",
                    "minItems",
                    path,
                    occurrence,
                    _mutated(walk.base, path, node[: floor - 1]),
                )
                _add(
                    walk,
                    "variant",
                    "minItems",
                    path,
                    occurrence,
                    _mutated(walk.base, path, node[:floor]),
                )
        item_schema = sch.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(node):
                _walk(walk, item_schema, item, [*path, index], f"{sp}.items")
    else:
        _scalar_cases(walk, sch, path, sp)


def generate_cases(schema_name: str, schema: dict[str, Any], base: Any) -> list[Case]:
    """Generate all mutants/variants/format-probes for one schema."""
    walk = _Walk(schema_name=schema_name, root_schema=schema, base=base)
    _walk(walk, schema, base, [], "$")
    return walk.cases


def assertive_keyword_occurrences(schema: Any) -> set[tuple[str, str]]:
    """Every violable keyword occurrence as ``(schema_pointer, keyword)``.

    Pointer grammar matches the walker's: property/definition names appear
    as ``.properties.<name>`` / ``.$defs.<name>``; array element schemas as
    ``.items``; conditionals as ``.allOf[i].then...``. ``if`` interiors are
    predicates and are skipped. ``additionalProperties: true`` is permissive
    (not violable) and therefore not an occurrence.
    """
    found: set[tuple[str, str]] = set()

    def visit(node: Any, pointer: str, in_name_map: bool) -> None:
        if not isinstance(node, dict):
            return
        for key, value in node.items():
            if in_name_map:
                visit(value, f"{pointer}.{key}", False)
                continue
            if key in {"properties", "$defs"}:
                visit(value, f"{pointer}.{key}", True)
                continue
            if key == "allOf":
                for index, branch in enumerate(value):
                    visit(branch, f"{pointer}.allOf[{index}]", False)
                continue
            if key == "if":
                continue  # predicate interior: selects, does not assert
            if key in {"items", "then"}:
                visit(value, f"{pointer}.{key}", False)
                continue
            if key == "additionalProperties":
                if value is False:
                    found.add((f"{pointer}.additionalProperties", key))
                elif isinstance(value, dict):
                    found.add((f"{pointer}.additionalProperties", key))
                    visit(value, f"{pointer}.additionalProperties", False)
                continue  # True is permissive: not violable
            if key in ANNOTATION_KEYWORDS or key == "$ref":
                continue
            # HANDLED keywords and anything unknown both land in the set;
            # unknown keywords then fail the meta-test's HANDLED check.
            found.add((f"{pointer}.{key}", key))

    visit(schema, "$", False)
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
