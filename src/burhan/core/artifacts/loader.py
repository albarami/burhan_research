"""Artifact loading and dumping with dual validation (PLAN v2 Fix 4a).

The governed JSON Schema is authoritative: every load validates the raw
instance against it FIRST (violations halt with the JSON path, AT-M01-1),
then constructs the typed model. A verdict disagreement between the two
validators — in either direction — is a loud :class:`IntegrityHalt`; no
artifact crosses a boundary on the model's opinion alone. Dumps re-validate
on the way out, so nothing schema-invalid can be serialized either.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError
from pydantic_core import PydanticSerializationError

from burhan.core.artifacts import canonical
from burhan.core.artifacts.models import (
    ArtifactModel,
    DecisionEntry,
    ProvenanceEntry,
    ReferenceComparisonReport,
    ResultsStoreEntry,
    RunManifest,
    StudyConfig,
)
from burhan.core.artifacts.schemas import check_instance
from burhan.core.errors import IntegrityHalt, halt

SCHEMA_FOR_MODEL: dict[type[ArtifactModel], str] = {
    StudyConfig: "study_config",
    ResultsStoreEntry: "results_store_entry",
    ProvenanceEntry: "provenance_entry",
    DecisionEntry: "decision_entry",
    RunManifest: "run_manifest",
    ReferenceComparisonReport: "reference_comparison",
}

MODEL_FOR_SCHEMA: dict[str, type[ArtifactModel]] = {
    name: model for model, name in SCHEMA_FOR_MODEL.items()
}


def _schema_name(model_cls: type[ArtifactModel]) -> str:
    name = SCHEMA_FOR_MODEL.get(model_cls)
    if name is None:
        halt(
            IntegrityHalt(
                "unregistered artifact model",
                report={"model": model_cls.__name__},
            )
        )
    return name


def validate_and_build[M: ArtifactModel](model_cls: type[M], instance: object) -> M:
    """Validate ``instance`` (governed schema first), return the typed model.

    Raises:
        IntegrityHalt: on schema violation (report carries the JSON path) or
            on model/schema divergence (schema accepted, model rejected).
    """
    name = _schema_name(model_cls)
    # Front door: the governed schemas cannot constrain freeform subtrees
    # (additionalProperties: true), so non-JSON content there must be caught
    # here, typed, with its path (REJECT fix 2).
    canonical.check_payload(instance)
    check_instance(name, instance)
    try:
        return model_cls.model_validate(instance)
    except ValidationError as exc:
        halt(
            IntegrityHalt(
                f"model/schema divergence for '{name}': governed schema accepted "
                "an instance the typed model rejects",
                report={
                    "schema": name,
                    "errors": [
                        {
                            "loc": ".".join(str(part) for part in error["loc"]),
                            "msg": error["msg"],
                            "type": error["type"],
                        }
                        for error in exc.errors()
                    ],
                },
            )
        )


def dump_canonical(model: ArtifactModel) -> str:
    """Serialize a model to canonical JSON, re-validating on the way out.

    Serialization failures (e.g. non-JSON content smuggled into a freeform
    field after construction) surface as :class:`IntegrityHalt`, never as an
    untyped pydantic error (REJECT fix 2).
    """
    try:
        payload = model.model_dump(mode="json", by_alias=True, exclude_unset=True)
    except PydanticSerializationError as exc:
        halt(
            IntegrityHalt(
                "artifact model produced non-serializable content",
                report={"model": type(model).__name__, "error": str(exc)},
            )
        )
    check_instance(_schema_name(type(model)), payload)
    return canonical.dumps(payload)


def load_yaml[M: ArtifactModel](path: Path, model_cls: type[M]) -> M:
    """Load a YAML artifact file into its typed, dually-validated model."""
    return validate_and_build(model_cls, _read(path, kind="yaml"))


def load_json[M: ArtifactModel](path: Path, model_cls: type[M]) -> M:
    """Load a JSON artifact file into its typed, dually-validated model."""
    return validate_and_build(model_cls, _read(path, kind="json"))


def _read(path: Path, *, kind: str) -> object:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        halt(
            IntegrityHalt(
                "artifact file unreadable",
                report={"path": str(path), "error": str(exc)},
            )
        )
    try:
        if kind == "json":
            return json.loads(text)
        return yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        halt(
            IntegrityHalt(
                f"artifact file is not valid {kind}",
                report={"path": str(path), "error": str(exc)},
            )
        )
