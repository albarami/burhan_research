"""Governed-schema registry (schemas/ at the repo root; doc-index item 05).

The six machine contracts are the runtime authority for every artifact
(schemas/00_README.md): instances are validated against them FIRST, and a
violation raises :class:`IntegrityHalt` carrying the JSON path of the
offending element (AT-M01-1).
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

# Untyped third-party edges (no stubs in the locked dependency set); the Any
# leakage is contained inside this module (standards §1 declared edges).
import yaml  # type: ignore[import-untyped]
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import best_match  # type: ignore[import-untyped]

from burhan.core.errors import IntegrityHalt, halt

GOVERNED_SCHEMA_FILES: dict[str, str] = {
    "study_config": "study_config.schema.yaml",
    "results_store_entry": "results_store.schema.json",
    "provenance_entry": "provenance_log.schema.json",
    "decision_entry": "decision_log.schema.json",
    "run_manifest": "run_manifest.schema.json",
    "reference_comparison": "reference_comparison.schema.json",
}


def schemas_dir() -> Path:
    """Location of the governed machine contracts (repo-root ``schemas/``)."""
    return Path(__file__).resolve().parents[4] / "schemas"


@cache
def load_schema(name: str) -> dict[str, Any]:
    """Load and cache one governed schema by registry name (read-only)."""
    if name not in GOVERNED_SCHEMA_FILES:
        halt(
            IntegrityHalt(
                "unknown governed schema",
                report={"schema": name, "known": sorted(GOVERNED_SCHEMA_FILES)},
            )
        )
    path = schemas_dir() / GOVERNED_SCHEMA_FILES[name]
    text = path.read_text(encoding="utf-8")
    loaded: dict[str, Any]
    if path.suffix == ".json":
        loaded = json.loads(text)
    else:
        loaded = yaml.safe_load(text)
    return loaded


@cache
def validator_for(name: str) -> Draft202012Validator:
    """Return the cached draft-2020-12 validator for a governed schema."""
    schema = load_schema(name)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def is_valid(name: str, instance: object) -> bool:
    """Governed-schema verdict on ``instance`` (used by conformance tests)."""
    return bool(validator_for(name).is_valid(instance))


def check_instance(name: str, instance: object) -> None:
    """Validate ``instance`` against the governed schema; halt with the path.

    Raises:
        IntegrityHalt: whose report names the schema, the JSON path of the
            most relevant violation, the failing keyword, and the message.
    """
    error = best_match(validator_for(name).iter_errors(instance))
    if error is not None:
        halt(
            IntegrityHalt(
                f"schema violation [{name}] at {error.json_path}: {error.message}",
                report={
                    "schema": name,
                    "path": error.json_path,
                    "keyword": str(error.validator),
                    "message": error.message,
                },
            )
        )
