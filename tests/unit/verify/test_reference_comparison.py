"""AT-M12-5: the reference-comparison builder (FR-1503).

Consumes a reference set + the real results store; emits a schema-valid
report with every divergence classified `unresolved` by default and
correct deltas. The reference is a comparison point, not ground truth.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from verify_util import FixedClock

from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import ReferenceComparisonReport
from burhan.core.errors import IntegrityHalt
from burhan.results.store import ResultsStore
from burhan.verify.reference_comparison import build_reference_comparison


def _store(tmp_path: Path) -> ResultsStore:
    store = ResultsStore(tmp_path / "results", FixedClock())
    store.write(
        {
            "id": "structural.path.F3->F1",
            "value": 0.563,
            "stage": "structural",
            "engine": "r_lavaan",
            "playbook_step": "PB-16",
        }
    )
    store.write(
        {
            "id": "measurement.reliability.F1.alpha",
            "value": 0.885,
            "stage": "measurement",
            "engine": "r_lavaan",
            "playbook_step": "PB-10",
        }
    )
    store.write(
        {
            "id": "effects.classification.X->Y.via_M",
            "value": "complementary",
            "stage": "effects",
            "engine": "r_lavaan",
            "playbook_step": "PB-17",
        }
    )
    return store


def _reference(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "study_id": "ref-study-2026",
        "source": {
            "description": "Prior manual SPSS/AMOS analysis (researcher-supplied).",
            "documents": [{"path": "inputs/manual_results.docx", "sha256": "a" * 64}],
            "caveats": "Manual item-handling may differ.",
        },
        "entries": entries,
    }


def _entry(
    comparison_id: str,
    *,
    stat_id: str,
    metric: str = "estimate",
    domain: str = "path",
    reference_value: Any = None,
    tolerance: float | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "comparison_id": comparison_id,
        "domain": domain,
        "metric": metric,
        "stat_id": stat_id,
    }
    if reference_value is not None:
        entry["reference_value"] = reference_value
    if tolerance is not None:
        entry["tolerance"] = tolerance
    return entry


def test_report_is_schema_valid_and_deltas_correct(tmp_path: Path) -> None:
    reference = _reference(
        [
            _entry("C1", stat_id="structural.path.F3->F1", reference_value=0.560, tolerance=0.01),
            _entry(
                "C2",
                stat_id="measurement.reliability.F1.alpha",
                domain="reliability",
                reference_value=0.91,
                tolerance=0.005,
            ),
            _entry(
                "C3",
                stat_id="effects.classification.X->Y.via_M",
                domain="effect",
                metric="classification",
                reference_value="complementary",
            ),
        ]
    )
    report = build_reference_comparison(reference, _store(tmp_path), run_id="run-0001")
    validate_and_build(ReferenceComparisonReport, report)
    by_id = {c["comparison_id"]: c for c in report["comparisons"]}
    # C1: |0.563 - 0.560| = 0.003 <= 0.01 -> match
    assert by_id["C1"]["status"] == "match"
    assert round(by_id["C1"]["delta"], 6) == 0.003
    # C2: |0.885 - 0.91| = 0.025 > 0.005 -> divergent, unresolved
    assert by_id["C2"]["status"] == "divergent"
    assert round(by_id["C2"]["delta"], 6) == -0.025
    assert by_id["C2"]["classification"] == "unresolved"
    # C3: string equality -> match, no delta
    assert by_id["C3"]["status"] == "match"
    assert "delta" not in by_id["C3"]
    assert report["summary"] == {
        "total": 3,
        "matches": 2,
        "divergent": 1,
        "reference_missing": 0,
        "burhan_only": 0,
        "unresolved": 1,
    }


def test_all_divergences_start_unresolved(tmp_path: Path) -> None:
    reference = _reference(
        [
            _entry("C1", stat_id="structural.path.F3->F1", reference_value=0.9, tolerance=0.001),
            _entry(
                "C2",
                stat_id="measurement.reliability.F1.alpha",
                domain="reliability",
                reference_value=0.2,
                tolerance=0.001,
            ),
        ]
    )
    report = build_reference_comparison(reference, _store(tmp_path), run_id="run-0002")
    validate_and_build(ReferenceComparisonReport, report)
    for comparison in report["comparisons"]:
        assert comparison["status"] == "divergent"
        assert comparison["classification"] == "unresolved"
    assert report["summary"]["unresolved"] == 2


def test_reference_without_value_is_reference_missing(tmp_path: Path) -> None:
    reference = _reference([_entry("C1", stat_id="structural.path.F3->F1")])
    report = build_reference_comparison(reference, _store(tmp_path), run_id="run-0003")
    validate_and_build(ReferenceComparisonReport, report)
    (comparison,) = report["comparisons"]
    assert comparison["status"] == "reference_missing"
    assert comparison["burhan_value"] == 0.563
    assert report["summary"]["reference_missing"] == 1


def test_unknown_stat_id_halts(tmp_path: Path) -> None:
    reference = _reference([_entry("C1", stat_id="structural.path.NOPE->X", reference_value=0.1)])
    with pytest.raises(IntegrityHalt) as excinfo:
        build_reference_comparison(reference, _store(tmp_path), run_id="run-0004")
    assert "unknown statistic id" in excinfo.value.message


def test_string_mismatch_is_divergent_without_delta(tmp_path: Path) -> None:
    reference = _reference(
        [
            _entry(
                "C1",
                stat_id="effects.classification.X->Y.via_M",
                domain="effect",
                metric="classification",
                reference_value="direct_only",
            )
        ]
    )
    report = build_reference_comparison(reference, _store(tmp_path), run_id="run-0005")
    (comparison,) = report["comparisons"]
    assert comparison["status"] == "divergent"
    assert comparison["classification"] == "unresolved"
    assert "delta" not in comparison


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.pop("entries"),
        lambda r: r["entries"].clear(),
        lambda r: r["entries"][0].pop("stat_id"),
        lambda r: r["entries"][0].update(tolerance="loose"),
        lambda r: r.pop("study_id"),
    ],
    ids=[
        "no_entries_key",
        "empty_entries",
        "missing_stat_id",
        "nonnumeric_tolerance",
        "no_study_id",
    ],
)
def test_malformed_reference_set_halts(tmp_path: Path, mutate: Any) -> None:
    reference = _reference([_entry("C1", stat_id="structural.path.F3->F1", reference_value=0.5)])
    mutate(reference)
    with pytest.raises(IntegrityHalt):
        build_reference_comparison(reference, _store(tmp_path), run_id="run-0006")
