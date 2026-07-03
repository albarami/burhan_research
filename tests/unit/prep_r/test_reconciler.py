"""Reconciler unit tests (AT-M08-6; FR-501).

The compare is cell-level at the policy tolerance (exactly 0): a planted
one-cell divergence halts VerificationHalt with a discrepancy report
naming row and column — never respondent values. Structural divergences
(columns, case sets, chain counts) halt named too.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest
from generator import build_golden

from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig
from burhan.core.errors import VerificationHalt
from burhan.core.policy import Policy
from burhan.prep.py_impl.pipeline import PrepResult, run_prep
from burhan.prep.reconciler import build_r_payload, reconcile_prep

REPO = Path(__file__).resolve().parents[3]


def _policy() -> Policy:
    return Policy.load(REPO / "policy" / "decision_policy.template.yaml", mode="certification")


@pytest.fixture(scope="module")
def golden_python(tmp_path_factory: pytest.TempPathFactory) -> tuple[Any, Any, PrepResult]:
    directory = tmp_path_factory.mktemp("golden-recon")
    golden = build_golden(11, with_defects=True)
    config = validate_and_build(StudyConfig, golden.config)
    result = run_prep(golden.write(directory), config, _policy())
    return golden, config, result


def _r_result_from(result: PrepResult) -> dict[str, Any]:
    """A faithful R-side result dict mirroring the Python frame."""
    cells = [
        [None if math.isnan(value) else float(value) for value in row]
        for row in result.frame.to_numpy().tolist()
    ]
    chain = {link.name: link.dropped_n for link in result.n_chain.links}
    return {
        "columns": list(result.frame.columns),
        "cases": list(result.frame.index),
        "cells": cells,
        "n_chain": {
            "raw_n": result.n_chain.raw_n,
            "final_n": result.n_chain.final_n,
            "dropped_by_link": chain,
        },
    }


def test_identical_results_reconcile_clean(golden_python: Any) -> None:  # AT-M08-6
    _, _, result = golden_python
    report = reconcile_prep(result, _r_result_from(result), policy=_policy())
    assert report["verdict"] == "match"
    assert report["tolerance"] == 0
    assert report["cells_compared"] == result.frame.shape[0] * result.frame.shape[1]


def test_planted_one_cell_divergence_halts_naming_row_and_column(
    golden_python: Any,
) -> None:  # AT-M08-6
    _, _, result = golden_python
    doctored = _r_result_from(result)
    row_index, column_index = 4, 7
    doctored["cells"][row_index][column_index] = (
        doctored["cells"][row_index][column_index] or 0.0
    ) + 1.0
    with pytest.raises(VerificationHalt) as excinfo:
        reconcile_prep(result, doctored, policy=_policy())
    assert "discrepancy" in excinfo.value.message
    details = excinfo.value.to_report()["details"]
    assert details["row"] == str(result.frame.index[row_index])
    assert details["column"] == str(result.frame.columns[column_index])
    assert excinfo.value.run_state == "HALTED_VERIFICATION"


def test_discrepancy_report_carries_no_respondent_values(golden_python: Any) -> None:
    _, _, result = golden_python
    doctored = _r_result_from(result)
    doctored["cells"][0][0] = (doctored["cells"][0][0] or 0.0) + 2.0
    with pytest.raises(VerificationHalt) as excinfo:
        reconcile_prep(result, doctored, policy=_policy())
    details = excinfo.value.to_report()["details"]
    assert set(details) <= {"row", "column", "kind"}  # metadata only, never values


def test_nonnumeric_r_cell_halts_typed_naming_row_and_column(
    golden_python: Any,
) -> None:  # REJECT-TC08b fix: raw ValueError probe ('not-a-number')
    _, _, result = golden_python
    doctored = _r_result_from(result)
    row_index, column_index = 3, 5
    doctored["cells"][row_index][column_index] = "not-a-number"
    with pytest.raises(VerificationHalt) as excinfo:  # typed, never ValueError
        reconcile_prep(result, doctored, policy=_policy())
    assert excinfo.value.run_state == "HALTED_VERIFICATION"
    details = excinfo.value.to_report()["details"]
    assert details["row"] == str(result.frame.index[row_index])
    assert details["column"] == str(result.frame.columns[column_index])
    assert set(details) <= {"kind", "row", "column"}  # metadata only
    assert "not-a-number" not in str(details)


def test_nan_versus_value_divergence_halts(golden_python: Any) -> None:  # AT-M08-6
    _, _, result = golden_python
    doctored = _r_result_from(result)
    # R reports a value where Python holds a missing cell: R_039's IN3
    row_index = list(result.frame.index).index("R_039")
    column_index = list(result.frame.columns).index("IN3")
    assert doctored["cells"][row_index][column_index] is None
    doctored["cells"][row_index][column_index] = 4.0
    with pytest.raises(VerificationHalt) as excinfo:
        reconcile_prep(result, doctored, policy=_policy())
    details = excinfo.value.to_report()["details"]
    assert details["row"] == "R_039"
    assert details["column"] == "IN3"


def test_column_order_divergence_halts_named(golden_python: Any) -> None:
    _, _, result = golden_python
    doctored = _r_result_from(result)
    doctored["columns"][0], doctored["columns"][1] = (
        doctored["columns"][1],
        doctored["columns"][0],
    )
    with pytest.raises(VerificationHalt) as excinfo:
        reconcile_prep(result, doctored, policy=_policy())
    assert excinfo.value.to_report()["details"]["kind"] == "columns"


def test_case_set_divergence_halts_named(golden_python: Any) -> None:
    _, _, result = golden_python
    doctored = _r_result_from(result)
    doctored["cases"] = doctored["cases"][:-1]
    doctored["cells"] = doctored["cells"][:-1]
    with pytest.raises(VerificationHalt) as excinfo:
        reconcile_prep(result, doctored, policy=_policy())
    assert excinfo.value.to_report()["details"]["kind"] == "cases"


def test_missing_cell_row_halts_named(golden_python: Any) -> None:
    _, _, result = golden_python
    doctored = _r_result_from(result)
    doctored["cells"] = doctored["cells"][:-1]  # cases list intact, rows short
    with pytest.raises(VerificationHalt) as excinfo:
        reconcile_prep(result, doctored, policy=_policy())
    assert excinfo.value.to_report()["details"]["kind"] == "cases"


def test_ragged_cell_row_halts_named(golden_python: Any) -> None:
    _, _, result = golden_python
    doctored = _r_result_from(result)
    doctored["cells"][2] = doctored["cells"][2][:-1]  # one row loses a column
    with pytest.raises(VerificationHalt) as excinfo:
        reconcile_prep(result, doctored, policy=_policy())
    assert excinfo.value.to_report()["details"]["kind"] == "columns"


def test_chain_count_divergence_halts_named(golden_python: Any) -> None:
    _, _, result = golden_python
    doctored = _r_result_from(result)
    doctored["n_chain"]["dropped_by_link"]["duplicates"] += 1
    with pytest.raises(VerificationHalt) as excinfo:
        reconcile_prep(result, doctored, policy=_policy())
    details = excinfo.value.to_report()["details"]
    assert details["kind"] == "n_chain"
    assert "duplicates" in str(details)


def test_r_payload_reads_policy_paths_not_literals(golden_python: Any) -> None:
    golden, config, _ = golden_python
    payload = build_r_payload(Path("/tmp/x.csv"), config, _policy())
    assert payload["policy"]["min_completion_pct"] == 90
    assert payload["policy"]["straightliner_min_block"] == 8
    assert payload["policy"]["duplicate_keys"] == ["response_id", "identical_model_vector"]
    assert payload["policy"]["outlier_treatment"] == "retain_with_sensitivity"
    items = payload["items"]
    assert [item["code"] for item in items] == [i.code for i in config.instrument.items]
    assert items[3] == {
        "code": "RS4",
        "column": "Q4_4",
        "min": 1,
        "max": 7,
        "reverse": True,
    }
    assert payload["attention_checks"] == [{"column": "Q9_4", "expected": "5"}]
