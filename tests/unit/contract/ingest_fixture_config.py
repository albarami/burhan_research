"""Minimal contract matching tests/fixtures/exports (V6 delegation tests)."""

from __future__ import annotations

import copy
from typing import Any

from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig

_SHA = "a" * 64

_BASE: dict[str, Any] = {
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
                "code": code,
                "text": text,
                "construct_ref": construct,
                "scale": {"type": "likert", "min": 1, "max": 7},
                "reverse_coded": False,
                "column_hint": hint,
            }
            for code, text, construct, hint in (
                ("RS1", "We have sufficient budget for the tool.", "RES", "Q4_1"),
                ("RS2", "Funding for the tool is secured.", "RES", "Q4_2"),
                ("CU1", "Our culture rewards experimentation.", "CUL", "Q5_1"),
                ("CU2", "New tools are welcomed here.", "CUL", "Q5_2"),
            )
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


def base_dict() -> dict[str, Any]:
    return copy.deepcopy(_BASE)


def base_config() -> StudyConfig:
    return validate_and_build(StudyConfig, base_dict())
