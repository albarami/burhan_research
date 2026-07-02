"""Crosswalk tests (AT-M05-1..4; FR-101–104; V6 zero-orphan rule).

Item codes are recovered from row-2 question text of the 3-header Qualtrics
export; every export column must resolve to exactly one declared role; the
raw frame is hashed immediately after load; csv and xlsx twins are
byte-equivalent at the crosswalk level. Reports name columns and codes,
never respondent values (standards §7).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from ingest_util import EXPORTS, fixture_config

from burhan.contract.crosswalk import Crosswalk, build_crosswalk
from burhan.core.errors import IntegrityHalt

CSV = EXPORTS / "adoption_3header.csv"
XLSX = EXPORTS / "adoption_3header.xlsx"


# -- AT-M05-1: complete crosswalk from embedded row-2 item codes ------------------


def test_three_header_fixture_yields_complete_crosswalk() -> None:  # AT-M05-1
    crosswalk = build_crosswalk(CSV, fixture_config())
    assert isinstance(crosswalk, Crosswalk)
    assert crosswalk.column_to_item == {
        "Q4_1": "RS1",
        "Q4_2": "RS2",
        "Q5_1": "CU1",
        "Q5_2": "CU2",
    }
    assert crosswalk.roles["ResponseId"] == "id"
    assert crosswalk.roles["Q3"] == "consent"
    assert crosswalk.roles["Q9_4"] == "attention_check"
    assert crosswalk.roles["Q42"] == "demographic"
    assert crosswalk.roles["Progress"] == "completion"
    assert crosswalk.roles["Finished"] == "completion"
    assert crosswalk.roles["StartDate"] == "metadata"
    assert crosswalk.n_data_rows == 3
    assert len(crosswalk.raw_frame_sha256) == 64


def test_ambiguous_and_duplicate_item_codes_halt_naming_columns() -> None:  # AT-M05-1
    with pytest.raises(IntegrityHalt) as excinfo:
        build_crosswalk(EXPORTS / "adoption_ambiguous.csv", fixture_config())
    details = excinfo.value.to_report()["details"]
    flat = json.dumps(details)
    assert "Q4_1" in flat and "Q4_2" in flat  # RS1 claimed by two columns
    assert "Q5_1" in flat  # one column embedding two codes


def test_crosswalk_payload_is_canonical_and_value_free() -> None:  # standards §7
    crosswalk = build_crosswalk(CSV, fixture_config())
    payload = crosswalk.to_payload()
    from burhan.core.artifacts.canonical import dumps

    rendered = dumps(payload)
    for respondent_value in ("R_001", "R_002", "R_003", "2026-06-01 09:00"):
        assert respondent_value not in rendered  # never respondent values


# -- AT-M05-2: zero-orphan accounting ----------------------------------------------


def test_undeclared_column_fails_named_and_declaring_it_passes() -> None:  # AT-M05-2
    with pytest.raises(IntegrityHalt) as excinfo:
        build_crosswalk(EXPORTS / "adoption_orphan.csv", fixture_config())
    assert "SneakyExtra" in str(excinfo.value.to_report()["details"])

    def declare_metadata(data: dict[str, Any]) -> None:
        data["data"]["metadata_columns"].append("SneakyExtra")

    crosswalk = build_crosswalk(EXPORTS / "adoption_orphan.csv", fixture_config(declare_metadata))
    assert crosswalk.roles["SneakyExtra"] == "metadata"

    def declare_ignored(data: dict[str, Any]) -> None:
        data["data"]["ignored_item_columns"] = ["SneakyExtra"]

    crosswalk = build_crosswalk(EXPORTS / "adoption_orphan.csv", fixture_config(declare_ignored))
    assert crosswalk.roles["SneakyExtra"] == "ignored_item"


def test_column_claimed_by_two_roles_halts() -> None:  # V6: exactly one role
    def double_claim(data: dict[str, Any]) -> None:
        data["data"]["metadata_columns"].append("Q42")  # Q42 is already a demographic

    with pytest.raises(IntegrityHalt) as excinfo:
        build_crosswalk(CSV, fixture_config(double_claim))
    assert "Q42" in str(excinfo.value.to_report()["details"])


# -- AT-M05-3: structural mismatch -------------------------------------------------


def test_declared_but_absent_item_column_is_structural_mismatch() -> None:  # AT-M05-3
    def add_r9(data: dict[str, Any]) -> None:
        data["instrument"]["items"].append(
            {
                "code": "R9",
                "text": "A declared item the export lacks.",
                "construct_ref": "RES",
                "scale": {"type": "likert", "min": 1, "max": 7},
                "reverse_coded": False,
            }
        )
        data["constructs"][0]["indicators"].append("R9")

    with pytest.raises(IntegrityHalt) as excinfo:
        build_crosswalk(CSV, fixture_config(add_r9))
    details = excinfo.value.to_report()["details"]
    assert "R9" in str(details)
    assert "structural" in excinfo.value.message


def test_missing_declared_role_columns_halt() -> None:  # FR-104
    def wrong_id_column(data: dict[str, Any]) -> None:
        data["data"]["id_column"] = "RespondentKey"  # not in the export

    with pytest.raises(IntegrityHalt) as excinfo:
        build_crosswalk(CSV, fixture_config(wrong_id_column))
    assert "RespondentKey" in str(excinfo.value.to_report()["details"])


# -- AT-M05-4: csv/xlsx parity ------------------------------------------------------


def test_xlsx_twin_produces_identical_crosswalk_and_hash() -> None:  # AT-M05-4
    def xlsx_format(data: dict[str, Any]) -> None:
        data["data"]["file"] = "inputs/adoption_3header.xlsx"
        data["data"]["format"] = "xlsx"

    from_csv = build_crosswalk(CSV, fixture_config())
    from_xlsx = build_crosswalk(XLSX, fixture_config(xlsx_format))
    assert from_csv.column_to_item == from_xlsx.column_to_item
    assert from_csv.roles == from_xlsx.roles
    assert from_csv.raw_frame_sha256 == from_xlsx.raw_frame_sha256
    csv_payload = from_csv.to_payload()
    xlsx_payload = from_xlsx.to_payload()
    # source_file legitimately differs (provenance names the actual file);
    # everything else must be identical.
    assert csv_payload.pop("source_file") == "adoption_3header.csv"
    assert xlsx_payload.pop("source_file") == "adoption_3header.xlsx"
    assert csv_payload == xlsx_payload


# -- file integrity -----------------------------------------------------------------


def test_missing_and_malformed_exports_halt(tmp_path: Path) -> None:  # FR-101/104
    with pytest.raises(IntegrityHalt):
        build_crosswalk(tmp_path / "absent.csv", fixture_config())

    def xlsx_format(data: dict[str, Any]) -> None:
        data["data"]["format"] = "xlsx"

    corrupt = tmp_path / "corrupt.xlsx"
    corrupt.write_bytes(b"not an xlsx at all")
    with pytest.raises(IntegrityHalt):
        build_crosswalk(corrupt, fixture_config(xlsx_format))


def test_format_extension_mismatch_halts(tmp_path: Path) -> None:
    # Contract says csv; caller hands an xlsx path — integrity, not guessing.
    with pytest.raises(IntegrityHalt) as excinfo:
        build_crosswalk(XLSX, fixture_config())
    assert "format" in excinfo.value.message


def test_duplicate_export_column_codes_halt(tmp_path: Path) -> None:  # FR-104
    rows = (CSV).read_text(encoding="utf-8").splitlines()
    header = rows[0].replace("Q4_2", "Q4_1")  # two columns named Q4_1
    doubled = tmp_path / "doubled.csv"
    doubled.write_text("\n".join([header, *rows[1:]]) + "\n", encoding="utf-8")
    with pytest.raises(IntegrityHalt) as excinfo:
        build_crosswalk(doubled, fixture_config())
    assert "Q4_1" in str(excinfo.value.to_report()["details"])


def test_non_utf8_csv_halts(tmp_path: Path) -> None:  # FR-101 integrity
    bad = tmp_path / "latin.csv"
    bad.write_bytes("ResponseId,Q3\nR_001,caf\xe9\n".encode("latin-1"))
    with pytest.raises(IntegrityHalt) as excinfo:
        build_crosswalk(bad, fixture_config())
    assert "unreadable" in excinfo.value.message


def test_too_few_rows_for_declared_headers_halts(tmp_path: Path) -> None:
    stub = tmp_path / "tiny.csv"
    stub.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(IntegrityHalt) as excinfo:
        build_crosswalk(stub, fixture_config())
    assert "header" in excinfo.value.message
