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
from ingest_util import (
    EXPORTS,
    dba_demographic_config,
    dba_fixture_config,
    fixture_config,
    single_header_config,
    write_synthetic_export,
)

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


@pytest.mark.parametrize("short_row_index", [1, 2])  # row 2 and row 3, 0-based
def test_ragged_header_rows_halt_typed_with_precise_report(
    tmp_path: Path, short_row_index: int
) -> None:  # REJECT-TC05 fixes 1-2
    lines = CSV.read_text(encoding="utf-8").splitlines()
    fields = lines[short_row_index].split(",")
    lines[short_row_index] = ",".join(fields[:-1])  # drop the last header cell
    ragged = tmp_path / "ragged.csv"
    ragged.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(IntegrityHalt) as excinfo:  # typed, never a raw ValueError
        build_crosswalk(ragged, fixture_config())
    details = excinfo.value.to_report()["details"]
    assert details["file"] == "ragged.csv"
    offending = details["ragged_header_rows"]
    assert offending == [{"row": short_row_index + 1, "expected_width": 11, "actual_width": 10}]
    # precise and value-free: no respondent cells in the report
    flat = json.dumps(details)
    for respondent_value in ("R_001", "R_002", "R_003"):
        assert respondent_value not in flat


def test_too_few_rows_for_declared_headers_halts(tmp_path: Path) -> None:
    stub = tmp_path / "tiny.csv"
    stub.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(IntegrityHalt) as excinfo:
        build_crosswalk(stub, fixture_config())
    assert "header" in excinfo.value.message


# -- TC-18: real 3-header Qualtrics export (header_rows undeclared) ------------------
#
# The DBA case: a 3-header Qualtrics export whose contract declares NEITHER
# header_rows NOR export_dialect, and whose non-modeled roles are declared by
# their embedded code (demographics `D1`, ignored `IGN1`) rather than the literal
# row-0 QID. The adoption fixture set header_rows=3 and used literal row-0 names,
# so it never exercised either mode.


def test_multiheader_modeled_items_resolve_without_header_rows() -> None:  # AT-M18-1
    crosswalk = build_crosswalk(EXPORTS / "dba_multiheader.csv", dba_fixture_config())
    assert crosswalk.header_rows == 3  # dialect auto-detected (row-2 ImportId signature)
    assert crosswalk.column_to_item == {
        "Q1_1": "RS1",
        "Q1_2": "RS2",
        "Q2_1": "CU1",
        "Q2_2": "CU2",
    }
    assert crosswalk.n_data_rows == 3


def test_multiheader_embedded_role_codes_resolve() -> None:  # AT-M18-2
    crosswalk = build_crosswalk(EXPORTS / "dba_multiheader.csv", dba_fixture_config())
    # embedded-code roles resolve to their row-0 columns…
    assert crosswalk.roles["Q40"] == "demographic"  # embedded `D1`
    assert crosswalk.roles["Q99"] == "ignored_item"  # embedded `IGN1`
    # …alongside literal row-0 roles, with no "declared column the export lacks" halt.
    assert crosswalk.roles["ResponseId"] == "id"
    assert crosswalk.roles["StartDate"] == "metadata"
    assert set(crosswalk.roles) == {
        "ResponseId",
        "Q1_1",
        "Q1_2",
        "Q2_1",
        "Q2_2",
        "Q40",
        "Q99",
        "StartDate",
    }


def test_multiheader_undeclared_column_still_orphans() -> None:  # AT-M18-3
    with pytest.raises(IntegrityHalt) as excinfo:
        build_crosswalk(EXPORTS / "dba_multiheader_orphan.csv", dba_fixture_config())
    assert "SneakyExtra" in str(excinfo.value.to_report()["details"])

    def declare_metadata(data: dict[str, Any]) -> None:
        data["data"]["metadata_columns"].append("SneakyExtra")

    crosswalk = build_crosswalk(
        EXPORTS / "dba_multiheader_orphan.csv", dba_fixture_config(declare_metadata)
    )
    assert crosswalk.roles["SneakyExtra"] == "metadata"


def test_multiheader_unstated_ambiguous_headers_halt() -> None:  # AT-M18-4
    # Multi-header shape, no ImportId signature, header_rows/export_dialect unset:
    # must halt typed — never silently parse as a single-header (the original bug).
    with pytest.raises(IntegrityHalt) as excinfo:
        build_crosswalk(EXPORTS / "dba_multiheader_nosignature.csv", dba_fixture_config())
    assert "header" in excinfo.value.message
    assert "structure" in excinfo.value.message


def test_single_header_plain_csv_resolves() -> None:  # AT-M18-5
    crosswalk = build_crosswalk(EXPORTS / "plain_single_header.csv", single_header_config())
    assert crosswalk.header_rows == 1
    assert crosswalk.column_to_item == {"SR1": "SR1", "SR2": "SR2", "SR3": "SR3", "SR4": "SR4"}
    assert crosswalk.roles["respondent"] == "id"
    assert crosswalk.roles["age"] == "demographic"
    assert crosswalk.n_data_rows == 3


def test_single_header_plain_csv_resolves_with_header_rows_omitted() -> None:  # AT-M18-5 regression
    # PLAN v1 §2 step 3: a plain single-header CSV with BOTH header_rows and export_dialect
    # unset must resolve as one header (row 0 already carries the item codes) — never halt.
    # The masked regression: AT-M18-5's fixture set header_rows: 1 explicitly, so the
    # omitted-header generic path went untested and wrongly halted.
    def omit_header_rows(data: dict[str, Any]) -> None:
        del data["data"]["header_rows"]

    crosswalk = build_crosswalk(
        EXPORTS / "plain_single_header.csv", single_header_config(omit_header_rows)
    )
    assert crosswalk.header_rows == 1
    assert crosswalk.column_to_item == {"SR1": "SR1", "SR2": "SR2", "SR3": "SR3", "SR4": "SR4"}
    assert crosswalk.roles["respondent"] == "id"
    assert crosswalk.roles["age"] == "demographic"
    assert crosswalk.n_data_rows == 3


# -- TC-18 negative controls: secondary-fix ambiguity + detector robustness ----------
#
# The secondary fix resolves a non-modeled role token by literal row-0 name OR by
# embedding in the code-bearing header row; its failure mode — a token that embeds in
# MORE THAN ONE column — must halt naming the columns, never silently take the first
# (FR-103/104). The primary fix's dialect auto-detector must likewise DECLINE a
# degenerate or non-Qualtrics header block rather than crash or false-positive into a
# 3-header read. AT-M18-4 covers the detector's third rejection route (row-3 is data
# that fails to parse as JSON); these two cover the short-circuit and JSON-non-ImportId
# routes, so every non-signature path is exercised.


def test_multiheader_embedded_role_token_ambiguous_halts_naming_columns() -> None:  # secondary fix
    # `D1` (declared demographic) is embedded in TWO row-1 cells (Q40 and Q99): the
    # resolver must halt naming both, never silently claim the first (FR-103/104).
    with pytest.raises(IntegrityHalt) as excinfo:
        build_crosswalk(EXPORTS / "dba_multiheader_ambiguous_role.csv", dba_fixture_config())
    assert "more than one" in excinfo.value.message
    details = excinfo.value.to_report()["details"]
    assert details["column"] == "D1"
    assert details["role"] == "demographic"
    assert details["columns"] == ["Q40", "Q99"]


def test_detector_declines_degenerate_short_export(tmp_path: Path) -> None:
    # Fewer than three rows, no dialect/header_rows declared: the signature check must
    # short-circuit (no IndexError on the absent third row) and the run halts typed.
    stub = tmp_path / "tiny_nodialect.csv"
    stub.write_text("ResponseId,Q1_1\nResponse ID,RS1 marker.\n", encoding="utf-8")
    with pytest.raises(IntegrityHalt) as excinfo:
        build_crosswalk(stub, dba_fixture_config())
    assert "header" in excinfo.value.message and "structure" in excinfo.value.message


def test_detector_declines_json_non_importid_third_row(tmp_path: Path) -> None:
    # Row 3 parses as JSON but is not Qualtrics ImportId metadata (bare numbers): the
    # detector must not false-positive into a 3-header read — it halts for a declaration.
    stub = tmp_path / "numeric_row3.csv"
    stub.write_text("ResponseId,Q1_1\nResponse ID,RS1 marker.\n1,2\n", encoding="utf-8")
    with pytest.raises(IntegrityHalt) as excinfo:
        build_crosswalk(stub, dba_fixture_config())
    assert "header" in excinfo.value.message and "structure" in excinfo.value.message


# -- TC-20: Qualtrics demographic selected-choice + text-sidecar resolution ----------
#
# A Qualtrics demographic with an "Other (please specify)" option produces TWO export
# columns: the selected-choice column and a `..._N_TEXT` free-text sidecar whose row-1
# text embeds the SAME demographic code. The crosswalk binds the demographic to the
# selected-choice column and accounts the `_TEXT` sidecar as ignored — while any OTHER
# multiplicity stays a real FR-103/104 ambiguity and every unpaired column still orphans.

_SIDECAR_DEMO = [{"code": "D3", "column_hint": "D3", "type": "categorical"}]


def test_demographic_choice_binds_and_text_sidecar_ignored() -> None:  # AT-M20-1 (RED-first)
    # Pre-fix: `D3` → {Q44, Q44_5_TEXT} halts FR-103/104. Post-fix: bind + ignore.
    crosswalk = build_crosswalk(
        EXPORTS / "dba_demographic_sidecar.csv", dba_demographic_config(_SIDECAR_DEMO)
    )
    assert crosswalk.roles["Q44"] == "demographic"  # selected-choice binds
    assert crosswalk.roles["Q44_5_TEXT"] == "ignored_item"  # "Other-specify" sidecar accounted
    assert crosswalk.n_data_rows == 3


def test_unlabelled_demographic_binds_via_literal_id() -> None:  # AT-M20-3 (RED-first)
    # Nationality's row-1 text carries no code, so the hint is the literal row-0 id
    # `Q45`. Pre-fix: `Q45_2_TEXT` is unaccounted → V6 orphan halt. Post-fix: accounted
    # by base-pairing (the sidecar is never a hit of `Q45`).
    demo = [{"code": "D4", "column_hint": "Q45", "type": "categorical"}]
    crosswalk = build_crosswalk(
        EXPORTS / "dba_demographic_unlabelled.csv", dba_demographic_config(demo)
    )
    assert crosswalk.roles["Q45"] == "demographic"
    assert crosswalk.roles["Q45_2_TEXT"] == "ignored_item"


def test_skipped_demographic_number_resolves_when_undeclared() -> None:  # AT-M20-4a (valid state)
    # Corrected source: D10 does not exist (survey skips D9→D11) and is NOT declared;
    # the export gap causes no halt. Passes pre & post fix.
    demo = [
        {"code": "D9", "column_hint": "D9", "type": "categorical"},
        {"code": "D11", "column_hint": "D11", "type": "ordinal"},
    ]
    crosswalk = build_crosswalk(
        EXPORTS / "dba_demographic_skipnum.csv", dba_demographic_config(demo)
    )
    assert crosswalk.roles["Q50"] == "demographic"
    assert crosswalk.roles["Q51"] == "demographic"


def test_still_declaring_absent_demographic_halts() -> None:  # AT-M20-4b (FR-104 guard)
    # A still-declared phantom D10 (the export has none) MUST halt FR-104 — FR-104
    # strictness is not weakened by TC-20.
    demo = [
        {"code": "D9", "column_hint": "D9", "type": "categorical"},
        {"code": "D11", "column_hint": "D11", "type": "ordinal"},
        {"code": "D10", "column_hint": "D10", "type": "ordinal"},
    ]
    with pytest.raises(IntegrityHalt) as excinfo:
        build_crosswalk(EXPORTS / "dba_demographic_skipnum.csv", dba_demographic_config(demo))
    details = excinfo.value.to_report()["details"]
    assert "the export lacks" in excinfo.value.message
    assert details["column"] == "D10"
    assert details["role"] == "demographic"


def test_demographic_two_nonsidecar_matches_halt(tmp_path: Path) -> None:  # AT-M20-2 (guard)
    # `D3` embeds in a choice column AND a `_TEXT` column whose base (`Q88`) is NOT a
    # co-hit → the collapse must NOT fire; real two-column ambiguity halts.
    path = write_synthetic_export(
        tmp_path / "crosswired.csv",
        [
            ("ResponseId", "Response ID"),
            ("Q1_1", "Resources - RS1. We have budget."),
            ("Q1_2", "Resources - RS2. Funding is secured."),
            ("Q2_1", "Culture - CU1. We reward experimentation."),
            ("Q2_2", "Culture - CU2. New tools welcomed."),
            ("Q30", "D3. What is your education level? - Selected Choice"),
            ("Q88_1_TEXT", "D3. Stray free text from another item - Text"),
            ("StartDate", "Start Date"),
        ],
    )
    with pytest.raises(IntegrityHalt) as excinfo:
        build_crosswalk(path, dba_demographic_config(_SIDECAR_DEMO))
    details = excinfo.value.to_report()["details"]
    assert "more than one" in excinfo.value.message
    assert details["column"] == "D3"
    assert details["columns"] == ["Q30", "Q88_1_TEXT"]


def test_text_named_column_without_marker_is_not_a_sidecar(
    tmp_path: Path,
) -> None:  # AT-M20-2 (dual-signal)
    # `Q44_9_TEXT` has the `_N_TEXT` id AND base `Q44` is a co-hit, but its row-1 text
    # has no "- Text" marker → NOT a sidecar (both signals required) → real ambiguity.
    path = write_synthetic_export(
        tmp_path / "marker_absent.csv",
        [
            ("ResponseId", "Response ID"),
            ("Q1_1", "Resources - RS1. We have budget."),
            ("Q1_2", "Resources - RS2. Funding is secured."),
            ("Q2_1", "Culture - CU1. We reward experimentation."),
            ("Q2_2", "Culture - CU2. New tools welcomed."),
            ("Q44", "D3. What is your education level? - Selected Choice"),
            ("Q44_9_TEXT", "D3. What is your education level duplicated - Selected Choice"),
            ("StartDate", "Start Date"),
        ],
    )
    with pytest.raises(IntegrityHalt) as excinfo:
        build_crosswalk(path, dba_demographic_config(_SIDECAR_DEMO))
    details = excinfo.value.to_report()["details"]
    assert "more than one" in excinfo.value.message
    assert details["columns"] == ["Q44", "Q44_9_TEXT"]


def test_unpaired_text_column_still_orphans(tmp_path: Path) -> None:  # AT-M20-5 (zero-orphan)
    # A `_TEXT` column not paired to any declared demographic base is NOT blanket-
    # ignored — it stays an orphan (V6). Declaring it ignored then passes.
    columns = [
        ("ResponseId", "Response ID"),
        ("Q1_1", "Resources - RS1. We have budget."),
        ("Q1_2", "Resources - RS2. Funding is secured."),
        ("Q2_1", "Culture - CU1. We reward experimentation."),
        ("Q2_2", "Culture - CU2. New tools welcomed."),
        ("Q47", "D6. What is your monthly income in QAR? - Selected Choice"),
        ("Q77_1_TEXT", "Stray free-text column from elsewhere - Text"),
        ("StartDate", "Start Date"),
    ]
    path = write_synthetic_export(tmp_path / "orphan_text.csv", columns)
    demo = [{"code": "D6", "column_hint": "D6", "type": "ordinal"}]
    with pytest.raises(IntegrityHalt) as excinfo:
        build_crosswalk(path, dba_demographic_config(demo))
    assert "unaccounted" in excinfo.value.message
    assert "Q77_1_TEXT" in str(excinfo.value.to_report()["details"])

    crosswalk = build_crosswalk(
        path,
        dba_demographic_config(
            demo, mutate=lambda d: d["data"].update({"ignored_item_columns": ["Q77_1_TEXT"]})
        ),
    )
    assert crosswalk.roles["Q47"] == "demographic"
    assert crosswalk.roles["Q77_1_TEXT"] == "ignored_item"


def test_nondemographic_role_ambiguity_still_halts(
    tmp_path: Path,
) -> None:  # AT-M20-2 (scope guard)
    # The collapse is demographic-scoped: a non-demographic role (ignored) resolving to
    # two columns still halts FR-103/104 (the generic `resolve()` path is unchanged).
    columns = [
        ("ResponseId", "Response ID"),
        ("Q1_1", "Resources - RS1. We have budget."),
        ("Q1_2", "Resources - RS2. Funding is secured."),
        ("Q2_1", "Culture - CU1. We reward experimentation."),
        ("Q2_2", "Culture - CU2. New tools welcomed."),
        ("Q60", "Out of model - IGN. Legacy one."),
        ("Q61", "Out of model - IGN. Legacy two."),
        ("StartDate", "Start Date"),
    ]
    path = write_synthetic_export(tmp_path / "ign_ambiguous.csv", columns)
    cfg = dba_demographic_config(
        [], mutate=lambda d: d["data"].update({"ignored_item_columns": ["IGN"]})
    )
    with pytest.raises(IntegrityHalt) as excinfo:
        build_crosswalk(path, cfg)
    details = excinfo.value.to_report()["details"]
    assert "more than one" in excinfo.value.message
    assert details["columns"] == ["Q60", "Q61"]
    assert details["role"] == "ignored_item"
