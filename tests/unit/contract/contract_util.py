"""Shared contract-test helpers: worked-example config with targeted mutations."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig
from burhan.core.artifacts.schemas import schemas_dir

REPO = Path(__file__).resolve().parents[3]
EXPORTS = REPO / "tests" / "fixtures" / "exports"


def example_dict() -> dict[str, Any]:
    loaded = yaml.safe_load(
        (schemas_dir() / "study_config.example.yaml").read_text(encoding="utf-8")
    )
    assert isinstance(loaded, dict)
    return loaded


def example_config(mutate: Any = None) -> StudyConfig:
    """The governed worked example, optionally mutated, schema-validated."""
    data = example_dict()
    if mutate is not None:
        mutate(data)
    return validate_and_build(StudyConfig, data)


def config_from(data: dict[str, Any]) -> StudyConfig:
    return validate_and_build(StudyConfig, copy.deepcopy(data))


# Reverse-coded items evidenced by the worked example's sources.
EXAMPLE_REVERSED = {"RS3", "CU3"}
