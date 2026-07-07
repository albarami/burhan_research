"""Mechanical enumeration of every study_config constraint and its Node A
prompt coverage (§7 exhaustive pass).

Walks ``study_config.schema.yaml`` for every declarative constraint (required
keys, ``additionalProperties: false`` blocks, patterns, enums, consts, ranges,
minItems, string-keyed maps, date-time formats) and pairs the imperative
cross-field validators V1-V7 + FR-204 with the prompt language that guarantees
Node A satisfies them. Each constraint resolves to COVERED, GAP, or ENGINE
(engine-injected provenance the adapter must never author).

Run as a script for the full checklist; :func:`coverage_rows` backs the
standing meta-test (``test_prompt_schema_coverage.py``) that fails if any
constraint is unmapped (a new schema constraint) or uncovered (a prompt
regression) — so this class of Node A halt cannot silently reopen.
"""

from __future__ import annotations

import datetime as dt
import sys
import types
from typing import Literal, Union, get_args, get_origin

import annotated_types as at
import yaml
from pydantic import BaseModel

from burhan.contract.node_a import default_template_path
from burhan.core.artifacts.models import StudyConfig
from burhan.core.artifacts.schemas import schemas_dir

ENGINE = "ENGINE"  # engine-injected (provenance); Node A must never author these
COVERED = "COVERED"
GAP = "GAP"
UNMAPPED = "UNMAPPED"
EXCLUDED = "EXCLUDED"  # a justified non-prompt constraint class (see TYPE_* below)

# `type` classification. A wrong container or scalar type cannot pass the
# structural rows already enumerated (no-extra / required / minItems) or is
# trivially satisfied by any YAML scalar, so these classes carry no prompt
# obligation of their own; they are enumerated and EXCLUDED with this reason.
# integer/boolean/number DO gate extraction (a float where an int is required
# halts), so each such field must map to a context-specific prompt phrase.
TYPE_TRIVIAL = {"string"}  # any documented YAML scalar satisfies type:string
TYPE_STRUCTURAL = {"object", "array"}  # covered by no-extra / required / minItems
TYPE_PROBES: dict[str, list[str]] = {
    "type:$.instrument.items[].scale.min": ["integer `min`"],
    "type:$.instrument.items[].scale.max": ["integer `max`"],
    "type:$.instrument.items[].reverse_coded": ["`reverse_coded` (a boolean)"],
    "type:$.data.header_rows": ["`header_rows` (an integer"],
    "type:$.protected_overrides.item_deletion_preauthorized": [
        "`item_deletion_preauthorized` (a boolean)"
    ],
}

# The one global statement that covers every additionalProperties:false block.
GLOBAL_NOEXTRA = "`additionalproperties: false` at every level"
ENGINE_SUBTREE = "$.meta.source_documents"
ENGINE_KEYS = {
    "$.meta": {"source_documents"},
    "$.methodology": {"playbook_id", "playbook_version"},
}

# Explicit probes for non-required/enum/no-extra constraints: each phrase (already
# lowercased) must appear in the whitespace-collapsed prompt for COVERED.
PROBES: dict[str, list[str]] = {
    "const:$.schema_version": ["the integer 1"],
    "pattern:$.meta.study_id": ["lowercase letters, digits, and hyphens", "no underscores"],
    "format:$.meta.created": ["do not emit `created`"],
    "range:$.data.header_rows": ["an integer 1 to 3"],
    "map:$.crosswalk.provided_map": ["mapping of export column name to item code"],
    "pattern:$.instrument.items[].code": ["letters, digits, underscores"],
    "pattern:$.constructs[].code": ["letters, digits, underscores"],
    "pattern:$.model.moderators[].on_path": ["form from->to in construct codes"],
    "pattern:$.hypotheses[].id": [
        "an `h` followed by one or more digits and an optional single lowercase letter",
        "never a descriptive suffix",
    ],
    "minItems:$.instrument.items": ["two or more item"],
    "minItems:$.constructs": ["one or more construct"],
    "minItems:$.constructs[].indicators": ["two or more of its item codes"],
    "minItems:$.constructs[].components": ["two or more of the first-order construct codes"],
    "minItems:$.model.exogenous": ["at least one exogenous"],
    "minItems:$.model.endogenous": ["at least one endogenous"],
    "minItems:$.model.controls[].on": ["every control targets at least one construct"],
    "minItems:$.hypotheses": ["one or more hypothesis"],
}

# Imperative cross-field validators (validators.py) — each rule paired with the
# prompt language that steers Node A to satisfy it.
VALIDATORS: dict[str, list[str]] = {
    "V1-construct_ref": ["first-order construct code the item measures"],
    # V2: indicators must EXIST in instrument.items AND the designed pool must
    # meet the playbook minimum — both, not the schema minItems:2 count alone.
    "V2-indicators-exist": ["also appears in `instrument.items`"],
    "V2-playbook-minimum": ["the designed pool must meet the playbook's minimum"],
    # V3-components RESOLUTION (each component resolves to a first-order code) —
    # distinct from the minItems:2 count phrase, so deleting either is caught.
    "V3-components": ["the first-order construct codes it subsumes"],
    "V3-biconditional": ["required if any construct is second-order"],
    # V4: via present for every indirect effect AND every model/hypothesis/via
    # construct reference resolves to a declared construct.
    "V4-refs-via": ["required for every `indirect` effect"],
    "V4-resolvable": ["must be one of the declared `constructs`"],
    "V5-reachable": ["must also appear as a declared `effect: direct` hypothesis"],
    "V5-unique": ["each hypothesis `id` is unique"],
    # V6: exact one-role / zero-orphan export-column accounting, not the
    # localized metadata_columns phrase.
    "V6-one-role": ["every export column resolves to exactly one role"],
    "V6-zero-orphan": ["an unaccounted column is an orphan"],
    "V7-reverse-source": ["come only from explicit statements"],
    "FR-204-dictionary": ["the data dictionary is authoritative"],
}


def _walk(node: object, path: str, out: list[tuple[str, str, object]]) -> None:
    if not isinstance(node, dict):
        return
    if isinstance(node.get("type"), str):  # every declared type (Fix 1a)
        out.append(("type", path, node["type"]))
    if node.get("type") == "object" or "properties" in node:
        if node.get("additionalProperties") is False:
            out.append(("no-extra", path, sorted((node.get("properties") or {}).keys())))
        if "required" in node:
            out.append(("required", path, sorted(node["required"])))
        if isinstance(node.get("additionalProperties"), dict):
            out.append(("map", path, node["additionalProperties"].get("type")))
        for key, sub in (node.get("properties") or {}).items():
            _walk(sub, f"{path}.{key}", out)
    for leaf in ("pattern", "enum", "const", "format"):
        if leaf in node:
            out.append((leaf, path, node[leaf]))
    if "minimum" in node or "maximum" in node:
        out.append(("range", path, (node.get("minimum"), node.get("maximum"))))
    if node.get("type") == "array" or "items" in node:
        if "minItems" in node:
            out.append(("minItems", path, node["minItems"]))
        if isinstance(node.get("items"), dict):
            _walk(node["items"], f"{path}[]", out)
    for sub in node.get("allOf", []):
        then = sub.get("then", {})
        if "required" in then:
            cond = sub.get("if", {}).get("properties", {})
            label = ",".join(f"{k}={v.get('const')}" for k, v in cond.items())
            out.append(("required-if", f"{path}[{label}]", sorted(then["required"])))


def schema_constraints() -> list[tuple[str, str, object]]:
    schema = yaml.safe_load(
        (schemas_dir() / "study_config.schema.yaml").read_text(encoding="utf-8")
    )
    out: list[tuple[str, str, object]] = []
    _walk(schema, "$", out)
    return out


def _core(ann: object) -> object:
    """Strip Annotated / Optional / list to the underlying type."""
    if hasattr(ann, "__metadata__"):  # Annotated[X, ...] (UtcSeconds, Sha256)
        return _core(get_args(ann)[0])
    origin = get_origin(ann)
    if origin in (Union, types.UnionType):
        args = [a for a in get_args(ann) if a is not type(None)]
        return _core(args[0]) if len(args) == 1 else ann
    if origin is list:
        return _core(get_args(ann)[0])
    return ann


def _schema_enum(node: dict) -> list[object] | None:
    if "enum" in node:
        return node["enum"]
    items = node.get("items")
    if isinstance(items, dict) and "enum" in items:
        return items["enum"]
    return None


# A pydantic Field constraint maps to the JSON-schema keyword it mirrors at the
# same path (Fix 1b): pattern->pattern, min_length->minItems (every constrained
# list field), ge->minimum, le->maximum.
_MODEL_TO_SCHEMA = {
    "pattern": "pattern",
    "min_length": "minItems",
    "ge": "minimum",
    "le": "maximum",
}


def _field_constraints(field: object) -> list[tuple[str, object]]:
    """(kind, value) for each pydantic Field constraint on a leaf field.

    Reads ``FieldInfo.metadata``: ``_PydanticGeneralMetadata.pattern`` for
    string patterns, and the ``annotated_types`` markers ``MinLen`` / ``Ge`` /
    ``Le`` for ``min_length`` / ``ge`` / ``le``.
    """
    out: list[tuple[str, object]] = []
    for m in getattr(field, "metadata", ()):
        pattern = getattr(m, "pattern", None)
        if pattern is not None:
            out.append(("pattern", pattern))
        if isinstance(m, at.MinLen):
            out.append(("min_length", m.min_length))
        if isinstance(m, at.Ge):
            out.append(("ge", m.ge))
        if isinstance(m, at.Le):
            out.append(("le", m.le))
    return out


def _model_walk(
    model_cls: type[BaseModel],
    schema_node: dict,
    path: str,
    div: list[str],
    strict: list[str],
    model_only: list[str],
) -> None:
    props = schema_node.get("properties", {})
    aliases = {(f.alias or n): f for n, f in model_cls.model_fields.items()}
    if set(aliases) != set(props):
        div.append(f"{path}: model keys {sorted(aliases)} != schema {sorted(props)}")
    for alias, field in aliases.items():
        sub = props.get(alias)
        if not isinstance(sub, dict):
            continue
        core = _core(field.annotation)
        if get_origin(core) is Literal:
            m_vals, s_vals = set(get_args(core)), set(_schema_enum(sub) or [])
            if s_vals and m_vals != s_vals:
                div.append(f"{path}.{alias}: model enum {m_vals} != schema {s_vals}")
        if core is dt.datetime:  # UtcSeconds: model-only UTC/whole-second strictness
            strict.append(f"{path}.{alias}")
        for kind, value in _field_constraints(field):  # each must mirror a schema row
            if sub.get(_MODEL_TO_SCHEMA[kind]) != value:
                model_only.append(f"{path}.{alias}:{kind}={value!r}")
        if isinstance(core, type) and issubclass(core, BaseModel):
            nested = sub.get("items", sub) if sub.get("type") == "array" else sub
            _model_walk(core, nested, f"{path}.{alias}", div, strict, model_only)


def _model_report() -> tuple[list[str], list[str], list[str]]:
    """(divergences, strict_fields, model_only): the pydantic model vs the schema.

    Both validate at runtime (``loader``), so a model-only constraint can halt a
    schema-passing response. ``divergences`` is empty when the model mirrors the
    schema (property sets + enums); ``strict_fields`` are model-only strictly
    validated fields (UtcSeconds) the schema under-specifies; ``model_only`` is
    every pydantic Field constraint (pattern/min_length/ge/le) NOT mirrored by a
    schema keyword at the same path — empty proves the schema walk already
    enumerates them, so introspecting the model adds no unseen prompt obligation.
    """
    schema = yaml.safe_load(
        (schemas_dir() / "study_config.schema.yaml").read_text(encoding="utf-8")
    )
    div: list[str] = []
    strict: list[str] = []
    model_only: list[str] = []
    _model_walk(StudyConfig, schema, "$", div, strict, model_only)
    return div, strict, model_only


def model_divergences() -> list[str]:
    return _model_report()[0]


def model_strict_fields() -> list[str]:
    return _model_report()[1]


def model_only_constraints() -> list[str]:
    return _model_report()[2]


def rendered_prompt() -> str:
    """Node A's prompt template, whitespace-collapsed and lowercased."""
    return " ".join(default_template_path().read_text(encoding="utf-8").split()).lower()


def _enum_probe(values: list[object]) -> list[str]:
    return [f"`{str(v).lower()}`" for v in values]


def _required_probe(path: str, keys: list[str]) -> list[str]:
    engine = ENGINE_KEYS.get(path, set())
    return [f"`{k}`" for k in keys if k not in engine]


def coverage_rows() -> list[tuple[str, str, list[str]]]:
    """(constraint_key, status, missing_phrases) for every schema + validator constraint."""
    prompt = rendered_prompt()
    rows: list[tuple[str, str, list[str]]] = []
    for kind, path, detail in schema_constraints():
        key = f"{kind}:{path}"
        if path.startswith(ENGINE_SUBTREE):
            rows.append((key, ENGINE, []))
            continue
        if kind == "type":
            if detail in TYPE_STRUCTURAL or detail in TYPE_TRIVIAL:  # justified exclusion
                rows.append((key, EXCLUDED, []))
                continue
            if key not in TYPE_PROBES:  # integer/boolean/number must carry a phrase
                rows.append((key, UNMAPPED, []))
                continue
            phrases = TYPE_PROBES[key]
        elif kind == "no-extra":
            phrases = [GLOBAL_NOEXTRA]
        elif kind == "required":
            phrases = _required_probe(path, detail)  # type: ignore[arg-type]
        elif kind == "required-if":
            phrases = (
                ["carries `indicators`"] if "first_order" in path else ["carries `components`"]
            )
        elif kind == "enum":
            phrases = _enum_probe(detail)  # type: ignore[arg-type]
        elif key in PROBES:
            phrases = PROBES[key]
        else:
            rows.append((key, UNMAPPED, []))
            continue
        missing = [p for p in phrases if p not in prompt]
        rows.append((key, GAP if missing else COVERED, missing))
    for name, phrases in VALIDATORS.items():
        missing = [p for p in phrases if p not in prompt]
        rows.append((f"validator:{name}", GAP if missing else COVERED, missing))
    for field in model_strict_fields():  # model-only strictness (UtcSeconds) => omit
        key_name = field.rsplit(".", 1)[-1]
        phrases = [f"do not emit `{key_name}`"]
        missing = [p for p in phrases if p not in prompt]
        rows.append((f"model-strict:{field}", GAP if missing else COVERED, missing))
    return rows


def main() -> int:
    rows = coverage_rows()
    statuses = (COVERED, GAP, UNMAPPED, ENGINE, EXCLUDED)
    tally = {s: sum(1 for _, st, _ in rows if st == s) for s in statuses}
    counts = " ".join(f"{s}={tally[s]}" for s in statuses)
    print(f"=== Node A prompt coverage: {len(rows)} constraints ===")
    print(counts + "\n")
    for key, status, missing in rows:
        mark = {COVERED: "OK  ", GAP: "GAP ", UNMAPPED: "????", ENGINE: "eng ", EXCLUDED: "excl"}[
            status
        ]
        print(f"  {mark} {key}")
        for phrase in missing:
            print(f"         missing: {phrase!r}")
    return 1 if tally[GAP] or tally[UNMAPPED] else 0


if __name__ == "__main__":
    sys.exit(main())
