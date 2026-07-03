"""Dual-path parity end to end (AT-M08-6; FR-501/1501).

The real R worker runs through the TC-04 harness (renv-asserted, seeded)
on the golden exports; the reconciler must find cell-for-cell agreement
at tolerance 0 — on the defect build, the clean twin, and under the
remove-outliers policy where both paths drop the planted outlier.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from generator import build_golden

from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig
from burhan.core.policy import Policy
from burhan.core.rworker import RWorker
from burhan.prep.py_impl.pipeline import run_prep
from burhan.prep.reconciler import build_r_payload, reconcile_prep

REPO = Path(__file__).resolve().parents[3]


def _policy(tmp_path: Path | None = None, mutate: Any = None) -> Policy:
    template = REPO / "policy" / "decision_policy.template.yaml"
    if mutate is None:
        return Policy.load(template, mode="certification")
    assert tmp_path is not None
    data = yaml.safe_load(template.read_text(encoding="utf-8"))
    mutate(data)
    path = tmp_path / "parity_policy.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return Policy.load(path, mode="certification")


def _r_prep(payload: dict[str, Any], run_dir: Path, call_id: str) -> dict[str, Any]:
    worker = RWorker()
    return worker.call("prep_worker", payload, call_id=call_id, run_dir=run_dir, seed=1)


def _dual_run(
    tmp_path: Path, *, with_defects: bool, policy: Policy, call_id: str
) -> dict[str, Any]:
    golden = build_golden(11, with_defects=with_defects)
    config = validate_and_build(StudyConfig, golden.config)
    csv_path = golden.write(tmp_path)
    python_result = run_prep(csv_path, config, policy)
    r_result = _r_prep(build_r_payload(csv_path, config, policy), tmp_path, call_id)
    return reconcile_prep(python_result, r_result, policy=policy)


def test_golden_defect_build_matches_cell_for_cell(tmp_path: Path) -> None:  # AT-M08-6
    report = _dual_run(tmp_path, with_defects=True, policy=_policy(), call_id="parity01")
    assert report["verdict"] == "match"
    assert report["tolerance"] == 0
    assert report["cases"] == 36
    assert report["cells_compared"] == 36 * 12


def test_clean_twin_matches_cell_for_cell(tmp_path: Path) -> None:  # AT-M08-6
    report = _dual_run(tmp_path, with_defects=False, policy=_policy(), call_id="parity02")
    assert report["verdict"] == "match"
    assert report["cases"] == 32


def test_remove_outlier_policy_matches_across_paths(tmp_path: Path) -> None:  # AT-M08-6
    def remove_policy(data: dict[str, Any]) -> None:
        data["prep"]["outliers"]["treatment"] = "remove_with_sensitivity"

    policy = _policy(tmp_path, remove_policy)
    report = _dual_run(tmp_path, with_defects=True, policy=policy, call_id="parity03")
    assert report["verdict"] == "match"
    assert report["cases"] == 35  # both paths dropped the planted outlier


def test_r_worker_is_deterministic(tmp_path: Path) -> None:
    golden = build_golden(11, with_defects=True)
    config = validate_and_build(StudyConfig, golden.config)
    csv_path = golden.write(tmp_path)
    payload = build_r_payload(csv_path, config, _policy())
    first = _r_prep(payload, tmp_path, "det1")
    second = _r_prep(payload, tmp_path, "det2")
    assert first == second


def test_missing_column_hint_halts_payload_build(tmp_path: Path) -> None:
    from burhan.core.errors import IntegrityHalt

    golden = build_golden(11)
    golden.config["instrument"]["items"][0].pop("column_hint")
    config = validate_and_build(StudyConfig, golden.config)
    with pytest.raises(IntegrityHalt) as excinfo:
        build_r_payload(tmp_path / "x.csv", config, _policy())
    assert "column hint" in excinfo.value.message
