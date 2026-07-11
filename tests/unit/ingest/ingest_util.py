"""Shared ingest-test helpers: the fixture study contract matching the exports."""

from __future__ import annotations

import copy
import csv
import json
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


def _likert(code: str, text: str, construct: str) -> dict[str, Any]:
    return {
        "code": code,
        "text": text,
        "construct_ref": construct,
        "scale": {"type": "likert", "min": 1, "max": 7},
        "reverse_coded": False,
    }


# Mirrors the real DBA contract's convention (TC-18): a 3-header Qualtrics export
# where NEITHER header_rows NOR export_dialect is declared (the crosswalk must
# detect the dialect), and the non-modeled roles are declared by their EMBEDDED
# code (demographics `D1`, ignored `IGN1`) rather than the literal row-0 QID —
# the mode the adoption fixture (literal row-0 names) never exercised.
_DBA_CONFIG: dict[str, Any] = {
    "schema_version": 1,
    "meta": {
        "study_id": "dba-multiheader-fixture",
        "title": "DBA multi-header ingest fixture",
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
            _likert("RS1", "We have budget.", "RES"),
            _likert("RS2", "Funding is secured.", "RES"),
            _likert("CU1", "We reward experimentation.", "CUL"),
            _likert("CU2", "New tools welcomed.", "CUL"),
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
        "file": "inputs/dba_multiheader.csv",
        "format": "csv",
        # NOTE: no export_dialect, no header_rows — the DBA-real omission the crosswalk resolves.
        "id_column": "ResponseId",  # literal row-0 identifier
        "demographics": [{"code": "firm_size", "column_hint": "D1", "type": "ordinal"}],  # embedded
        "ignored_item_columns": ["IGN1"],  # embedded
        "metadata_columns": ["StartDate"],  # literal row-0 identifier
    },
}


def dba_fixture_config(mutate: Any = None) -> StudyConfig:
    """DBA-style contract matching `dba_multiheader.csv` (embedded-code roles,
    no declared header_rows/export_dialect)."""
    data = copy.deepcopy(_DBA_CONFIG)
    if mutate is not None:
        mutate(data)
    return validate_and_build(StudyConfig, data)


# A plain single-header CSV (item codes as literal row-0 headers) — the
# non-Qualtrics case that must keep resolving (TC-18 AT-M18-5, no regression).
_SINGLE_HEADER_CONFIG: dict[str, Any] = {
    "schema_version": 1,
    "meta": {
        "study_id": "single-header-fixture",
        "title": "Single-header ingest fixture",
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
            _likert("SR1", "Resources item one.", "RES"),
            _likert("SR2", "Resources item two.", "RES"),
            _likert("SR3", "Culture item one.", "CUL"),
            _likert("SR4", "Culture item two.", "CUL"),
        ]
    },
    "constructs": [
        {
            "code": "RES",
            "name": "Resources",
            "level": "first_order",
            "measurement": "reflective",
            "indicators": ["SR1", "SR2"],
        },
        {
            "code": "CUL",
            "name": "Culture",
            "level": "first_order",
            "measurement": "reflective",
            "indicators": ["SR3", "SR4"],
        },
    ],
    "model": {"exogenous": ["RES"], "endogenous": ["CUL"]},
    "hypotheses": [
        {"id": "H1", "effect": "direct", "from": "RES", "to": "CUL", "sign": "positive"}
    ],
    "data": {
        "file": "inputs/plain_single_header.csv",
        "format": "csv",
        "header_rows": 1,  # explicit single header
        "id_column": "respondent",
        "demographics": [{"code": "age", "column_hint": "age", "type": "numeric"}],
    },
}


def single_header_config(mutate: Any = None) -> StudyConfig:
    """Contract matching `plain_single_header.csv` (codes as literal row-0 headers)."""
    data = copy.deepcopy(_SINGLE_HEADER_CONFIG)
    if mutate is not None:
        mutate(data)
    return validate_and_build(StudyConfig, data)


def dba_demographic_config(demographics: list[dict[str, Any]], mutate: Any = None) -> StudyConfig:
    """A DBA-style contract for the TC-20 demographic-crosswalk fixtures: the four
    embedded modeled items + literal id/metadata columns, the given ``demographics``,
    and no ``ignored_item_columns`` (each fixture declares only its own columns)."""

    def _apply(data: dict[str, Any]) -> None:
        data["data"]["demographics"] = demographics
        data["data"].pop("ignored_item_columns", None)
        if mutate is not None:
            mutate(data)

    return dba_fixture_config(_apply)


def write_synthetic_export(
    path: Path, columns: list[tuple[str, str]], n_data_rows: int = 3
) -> Path:
    """Write a synthetic 3-header Qualtrics-style export (row 0 = QIDs, row 1 =
    question text carrying embedded codes, row 2 = ImportId signature) plus
    ``n_data_rows`` synthetic data rows. ``columns`` is a list of ``(qid, row1_text)``.
    All values are synthetic — never respondent data (standards §7)."""
    qids = [qid for qid, _ in columns]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(qids)
        writer.writerow([text for _, text in columns])
        writer.writerow([json.dumps({"ImportId": qid}) for qid in qids])
        for row in range(n_data_rows):
            writer.writerow([str(row + 1)] * len(qids))
    return path
