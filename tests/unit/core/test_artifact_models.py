"""Artifact model tests (AT-M01-1; FR-203 pattern; NFR-201).

Every governed schema loads; a valid instance round-trips
model -> canonical JSON -> model byte-identically; an invalid instance raises
with the schema path. The governed JSON Schema is authoritative: every load
runs it first, and model/schema verdict disagreement is a loud IntegrityHalt
(PLAN v2 Fix 4a).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import pytest
import yaml
from artifact_instances import valid_instance
from jsonschema import Draft202012Validator

from burhan.core.artifacts.loader import (
    MODEL_FOR_SCHEMA,
    ArtifactModel,
    dump_canonical,
    load_json,
    load_yaml,
    validate_and_build,
)
from burhan.core.artifacts.schemas import GOVERNED_SCHEMA_FILES, load_schema, schemas_dir
from burhan.core.errors import IntegrityHalt

EXAMPLE_STUDY_CONFIG = schemas_dir() / "study_config.example.yaml"


def _valid(name: str) -> dict[str, Any]:
    if name == "study_config":
        loaded = yaml.safe_load(EXAMPLE_STUDY_CONFIG.read_text(encoding="utf-8"))
        assert isinstance(loaded, dict)
        return loaded
    return valid_instance(name)


def test_every_governed_schema_loads() -> None:  # AT-M01-1
    assert sorted(GOVERNED_SCHEMA_FILES) == [
        "decision_entry",
        "provenance_entry",
        "reference_comparison",
        "results_store_entry",
        "run_manifest",
        "study_config",
    ]
    for name in sorted(GOVERNED_SCHEMA_FILES):
        schema = load_schema(name)
        Draft202012Validator.check_schema(schema)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_registry_covers_every_schema_with_a_model() -> None:
    assert sorted(MODEL_FOR_SCHEMA) == sorted(GOVERNED_SCHEMA_FILES)


def test_unknown_schema_name_halts() -> None:
    with pytest.raises(IntegrityHalt):
        load_schema("not_a_governed_schema")


@pytest.mark.parametrize("name", sorted(GOVERNED_SCHEMA_FILES))
def test_valid_instance_round_trips_byte_identically(name: str) -> None:  # AT-M01-1
    instance = _valid(name)
    model_cls = MODEL_FOR_SCHEMA[name]
    first = validate_and_build(model_cls, instance)
    dumped_1 = dump_canonical(first)
    second = validate_and_build(model_cls, json.loads(dumped_1))
    dumped_2 = dump_canonical(second)
    assert dumped_1.encode("utf-8") == dumped_2.encode("utf-8")
    assert first == second


_INVALID_MUTATIONS: list[tuple[str, list[str | int], Any, str]] = [
    # (schema, path to mutate, bad value, expected json_path in the report)
    ("study_config", ["hypotheses", 0, "id"], "X1", "$.hypotheses[0].id"),
    ("results_store_entry", ["stage"], "narrate", "$.stage"),
    ("provenance_entry", ["seq"], 0, "$.seq"),
    ("run_manifest", ["run_id"], "2026-07-02T09:00:00Z", "$.run_id"),
    ("reference_comparison", ["summary", "total"], 0, "$.summary.total"),
]


@pytest.mark.parametrize(("name", "path", "bad", "expected_path"), _INVALID_MUTATIONS)
def test_invalid_instance_raises_with_schema_path(  # AT-M01-1
    name: str, path: list[str | int], bad: Any, expected_path: str
) -> None:
    instance = _valid(name)
    target: Any = instance
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = bad
    with pytest.raises(IntegrityHalt) as excinfo:
        validate_and_build(MODEL_FOR_SCHEMA[name], instance)
    report = excinfo.value.to_report()["details"]
    assert report["schema"] == name
    assert report["path"] == expected_path


def test_unknown_field_raises_with_object_path() -> None:  # additionalProperties
    instance = _valid("decision_entry")
    instance["smuggled"] = 1
    with pytest.raises(IntegrityHalt) as excinfo:
        validate_and_build(MODEL_FOR_SCHEMA["decision_entry"], instance)
    assert excinfo.value.to_report()["details"]["path"] == "$"


def test_model_schema_divergence_is_loud(monkeypatch: pytest.MonkeyPatch) -> None:  # Fix 4a
    from burhan.core.artifacts import loader as loader_module

    class Divergent(ArtifactModel):
        schema_version: Literal[1]

    monkeypatch.setitem(loader_module.SCHEMA_FOR_MODEL, Divergent, "provenance_entry")
    with pytest.raises(IntegrityHalt) as excinfo:
        validate_and_build(Divergent, _valid("provenance_entry"))
    assert "divergence" in excinfo.value.message


def test_unregistered_model_class_halts() -> None:
    class Orphan(ArtifactModel):
        schema_version: Literal[1]

    with pytest.raises(IntegrityHalt):
        validate_and_build(Orphan, {"schema_version": 1})


def test_load_yaml_and_load_json_round_trip(tmp_path: Path) -> None:
    model_cls = MODEL_FOR_SCHEMA["study_config"]
    from_disk = load_yaml(EXAMPLE_STUDY_CONFIG, model_cls)
    as_json = tmp_path / "study_config.json"
    as_json.write_text(dump_canonical(from_disk) + "\n", encoding="utf-8")
    reloaded = load_json(as_json, model_cls)
    assert dump_canonical(reloaded) == dump_canonical(from_disk)


def test_load_yaml_missing_file_halts(tmp_path: Path) -> None:
    with pytest.raises(IntegrityHalt):
        load_yaml(tmp_path / "absent.yaml", MODEL_FOR_SCHEMA["study_config"])


def test_load_yaml_malformed_content_halts(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("{unbalanced: [", encoding="utf-8")
    with pytest.raises(IntegrityHalt):
        load_yaml(bad, MODEL_FOR_SCHEMA["study_config"])


def test_dump_validates_write_side() -> None:
    # Nothing schema-invalid can be serialized out: corrupt a built model via
    # object.__setattr__ (bypassing pydantic) and watch the dump halt.
    entry = validate_and_build(MODEL_FOR_SCHEMA["provenance_entry"], _valid("provenance_entry"))
    object.__setattr__(entry, "seq", 0)
    with pytest.raises(IntegrityHalt):
        dump_canonical(entry)


def test_non_json_payload_halts_at_load_with_path() -> None:  # REJECT fix 2
    decision = valid_instance("decision_entry")
    decision["inputs"] = {"bad": object()}
    with pytest.raises(IntegrityHalt) as excinfo:
        validate_and_build(MODEL_FOR_SCHEMA["decision_entry"], decision)
    assert "$.inputs.bad" in str(excinfo.value.to_report()["details"].get("path", ""))


def test_dump_canonical_wraps_serialization_failures() -> None:  # REJECT fix 2
    entry = validate_and_build(MODEL_FOR_SCHEMA["provenance_entry"], _valid("provenance_entry"))
    object.__setattr__(entry, "details", {"bad": object()})
    with pytest.raises(IntegrityHalt):  # never a bare PydanticSerializationError
        dump_canonical(entry)


def test_defaults_match_schema_defaults() -> None:  # Fix 4b default-agreement seed
    decision = valid_instance("decision_entry")
    del decision["protected"]
    model = validate_and_build(MODEL_FOR_SCHEMA["decision_entry"], decision)
    assert model.protected is False  # type: ignore[attr-defined]
