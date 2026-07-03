"""Golden-generator core tests (FR-1501 foundation; TC-08a subset).

The generator is deterministic (injected seed, no ambient RNG), emits a
schema-valid study config, a Qualtrics-dialect 3-header export, and a
ground-truth manifest per planted defect class. The clean twin carries no
defects at all.
"""

from __future__ import annotations

import csv
from pathlib import Path

from generator import DEFECT_CLASSES, build_golden, build_missingness_fixture

from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig


def test_same_seed_reproduces_rows_and_manifest_exactly() -> None:
    a = build_golden(11, with_defects=True)
    b = build_golden(11, with_defects=True)
    assert a.rows == b.rows
    assert a.manifest == b.manifest
    assert a.config == b.config


def test_different_seed_changes_the_data() -> None:
    assert build_golden(11).rows != build_golden(12).rows


def test_config_is_schema_valid() -> None:
    config = validate_and_build(StudyConfig, build_golden(11).config)
    assert config.meta.study_id.startswith("golden-")
    reversed_items = {i.code for i in config.instrument.items if i.reverse_coded}
    assert reversed_items == {"RS4", "CU4"}


def test_clean_twin_has_no_defects() -> None:
    clean = build_golden(11, with_defects=False)
    assert all(not entries for entries in clean.manifest.values())
    header, data = clean.rows[:3], clean.rows[3:]
    assert len(header) == 3
    ids = [row[0] for row in data]
    assert len(ids) == len(set(ids))  # no duplicate ids
    item_columns = range(2, 14)  # Q4_1..Q6_4 sit after ResponseId, Q3
    for row in data:
        for column in item_columns:
            assert row[column] != ""  # complete
            assert 1 <= int(row[column]) <= 7  # in range


def test_defect_build_covers_every_planted_class() -> None:
    golden = build_golden(11, with_defects=True)
    assert set(golden.manifest) == set(DEFECT_CLASSES)
    for defect_class in DEFECT_CLASSES:
        assert golden.manifest[defect_class], f"{defect_class} not planted"

    data = golden.rows[3:]
    by_id = {}
    for row in data:
        by_id.setdefault(row[0], []).append(row)

    # duplicates: the planted id occurs twice; the vector twin matches its source
    dup_id = golden.manifest["duplicates"][0]["response_id"]
    assert len(by_id[dup_id]) == 2
    # attention fail: planted case answers something other than the expected 5
    attention_case = golden.manifest["attention_fails"][0]["case"]
    assert by_id[attention_case][0][14] != "5"
    # out-of-range: every planted cell is outside 1..7
    for entry in golden.manifest["out_of_range"]:
        row = by_id[entry["case"]][0]
        value = row[golden.column_index(entry["item"])]
        assert value != "" and (not value.isdigit() or not 1 <= int(value) <= 7)
    # un-reversed: CU4 planted; its stored data differs from the clean twin's
    assert golden.manifest["un_reversed"] == [{"item": "CU4"}]
    # partials: the dropped partial misses more cells than the recovered one
    dropped = golden.manifest["partials_dropped"][0]["case"]
    recovered = golden.manifest["partials_recovered"][0]["case"]
    missing = {
        case: sum(1 for column in range(2, 14) if by_id[case][0][column] == "")
        for case in (dropped, recovered)
    }
    assert missing[recovered] == 1  # 11/12 ≈ 91.7% ≥ policy 90
    assert missing[dropped] >= 3  # ≤ 75% < policy 90
    # outliers: planted case sits at the scale extremes on most items
    outlier_case = golden.manifest["known_outliers"][0]["case"]
    extremes = [int(v) for v in by_id[outlier_case][0][2:14] if v != ""]
    assert sum(value >= 6 for value in extremes) >= 10


def test_written_csv_round_trips(tmp_path: Path) -> None:
    golden = build_golden(11)
    path = golden.write(tmp_path)
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [list(row) for row in csv.reader(handle)]
    assert rows == golden.rows


def test_missingness_fixtures_are_deterministic_and_distinct() -> None:
    mcar = build_missingness_fixture("mcar", 7)
    mnar = build_missingness_fixture("mnar", 7)
    assert mcar.rows == build_missingness_fixture("mcar", 7).rows
    data_mcar = mcar.rows[3:]
    data_mnar = mnar.rows[3:]
    assert any("" in row[2:14] for row in data_mcar)  # has missing cells
    assert any("" in row[2:14] for row in data_mnar)
    assert data_mcar != data_mnar
    assert mcar.manifest["engineered_missingness"]
    mnar_items = {entry["item"] for entry in mnar.manifest["engineered_missingness"]}
    assert mnar_items <= {"CU2", "RS1", "RS2"} and "CU2" in mnar_items
