"""AT-M11-1: fit indices match lavaan reference outputs (FR-801; PB-15).

Anchor: Mplus User's Guide ex5.11 (see PROVENANCE.md) — data committed
verbatim; printed values reproduced by the renv-locked lavaan to
printed precision before these tests were written. Pins use
round-to-printed-precision equality (cross-host stable, as in the
AT-M10-1 benchmark).
"""

from __future__ import annotations

from pathlib import Path

from structural_util import benchmark_config, benchmark_frame, playbook

from burhan.core.rworker import RWorker
from burhan.stats.structural import run_structural

# Printed Mplus reference values, reproduced by lavaan 0.6-21 (PROVENANCE.md)
PUBLISHED_FIT = {
    "chisq": 53.704,
    "df": 50,
    "pvalue": 0.3344,
    "cfi": 0.997,
    "tli": 0.997,
    "rmsea": 0.012,
    "rmsea_ci_lower": 0.000,
    "rmsea_ci_upper": 0.032,
    "srmr": 0.027,
}
PUBLISHED_PATHS = {("F3", "F1"): 0.563, ("F3", "F2"): 0.790, ("F4", "F3"): 0.473}


def _run(tmp_path: Path) -> dict:
    return run_structural(
        benchmark_frame(),
        benchmark_config(),
        playbook=playbook(),
        rworker=RWorker(),
        run_dir=tmp_path,
        call_id="bench-sem",
    )


def test_fit_indices_match_lavaan_reference(tmp_path: Path) -> None:
    fit = _run(tmp_path)["fit"]
    assert fit["df"] == PUBLISHED_FIT["df"]
    assert round(fit["pvalue"], 4) == PUBLISHED_FIT["pvalue"]
    for key in ("chisq", "cfi", "tli", "rmsea", "rmsea_ci_lower", "rmsea_ci_upper", "srmr"):
        assert round(fit[key], 3) == PUBLISHED_FIT[key], key


def test_structural_paths_match_published_estimates(tmp_path: Path) -> None:
    report = _run(tmp_path)
    paths = {(entry["lhs"], entry["rhs"]): entry["est"] for entry in report["paths"]}
    assert set(paths) == set(PUBLISHED_PATHS)
    for key, published in PUBLISHED_PATHS.items():
        assert round(paths[key], 3) == published, key


def test_band_evaluation_recorded_as_report(tmp_path: Path) -> None:
    # PB-15 failure_action is `report`: the evaluation carries the governed
    # action and a verdict per criterion; the ex5.11 fit lands in the good
    # tiers everywhere.
    evaluation = _run(tmp_path)["band_evaluation"]
    assert evaluation["action"] == "report"
    verdicts = {entry["criterion"]: entry["verdict"] for entry in evaluation["entries"]}
    assert verdicts == {
        "normed_chisq": "pass",
        "cfi_floor": "good",
        "tli_floor": "pass",
        "rmsea_ceiling": "good",
        "srmr_ceiling": "pass",
    }
    for entry in evaluation["entries"]:
        assert set(entry) >= {"criterion", "observed", "threshold", "verdict"}


def test_no_higher_order_means_no_carrier_block(tmp_path: Path) -> None:
    # The ex5.11 contract declares no higher-order construct: the carrier
    # record is absent rather than fabricated.
    report = _run(tmp_path)
    assert report["carrier"] is None
