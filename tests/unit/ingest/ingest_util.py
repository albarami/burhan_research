"""Shared ingest-test helpers: the fixture study contract matching the exports."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig

REPO = Path(__file__).resolve().parents[3]
EXPORTS = REPO / "tests" / "fixtures" / "exports"

_SHA = "a" * 64

_BASE_CONFIG: dict[str, Any] = {
    "schema_version": 1,
    "meta": {
        "study_id": "adoption-fixture-2026",
        "title": "Ingest fixture study",
        "source_documents": [
            {"role": "study_document", "path": "inputs/study.docx", "sha256": _SHA}
        ],
    },
    "methodology": {
        "declared": "CB_SEM",
        "playbook_id": "CB_SEM_PLAYBOOK",
        "playbook_version": "1.0",
        "design": "cross_sectional",
    },
    "instrument": {
        "items": [
            {
                "code": "RS1",
                "text": "We have sufficient budget for the tool.",
                "construct_ref": "RES",
                "scale": {"type": "likert", "min": 1, "max": 7},
                "reverse_coded": False,
                "column_hint": "Q4_1",
            },
            {
                "code": "RS2",
                "text": "Funding for the tool is secured.",
                "construct_ref": "RES",
                "scale": {"type": "likert", "min": 1, "max": 7},
                "reverse_coded": False,
                "column_hint": "Q4_2",
            },
            {
                "code": "CU1",
                "text": "Our culture rewards experimentation.",
                "construct_ref": "CUL",
                "scale": {"type": "likert", "min": 1, "max": 7},
                "reverse_coded": False,
                "column_hint": "Q5_1",
            },
            {
                "code": "CU2",
                "text": "New tools are welcomed here.",
                "construct_ref": "CUL",
                "scale": {"type": "likert", "min": 1, "max": 7},
                "reverse_coded": False,
                "column_hint": "Q5_2",
            },
        ]
    },
    "constructs": [
        {
            "code": "RES",
            "name": "Resources",
            "level": "first_order",
            "measurement": "reflective",
            "indicators": ["RS1", "RS2"],
        },
        {
            "code": "CUL",
            "name": "Culture",
            "level": "first_order",
            "measurement": "reflective",
            "indicators": ["CU1", "CU2"],
        },
    ],
    "model": {"exogenous": ["RES"], "endogenous": ["CUL"]},
    "hypotheses": [
        {"id": "H1", "effect": "direct", "from": "RES", "to": "CUL", "sign": "positive"}
    ],
    "data": {
        "file": "inputs/adoption_3header.csv",
        "format": "csv",
        "export_dialect": "qualtrics",
        "header_rows": 3,
        "id_column": "ResponseId",
        "consent_column": "Q3",
        "completion": {"progress_column": "Progress", "finished_column": "Finished"},
        "attention_checks": [{"column": "Q9_4", "expected": "5"}],
        "demographics": [{"code": "firm_size", "column_hint": "Q42", "type": "ordinal"}],
        "metadata_columns": ["StartDate"],
    },
}


def fixture_config(mutate: Any = None) -> StudyConfig:
    """The validated fixture contract; optionally mutated before validation."""
    data = copy.deepcopy(_BASE_CONFIG)
    if mutate is not None:
        mutate(data)
    return validate_and_build(StudyConfig, data)
