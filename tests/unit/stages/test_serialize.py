"""TC-15 store-row serialization (``burhan.stages.serialize``).

Each family's rows must (a) carry grammar-valid ids the store accepts and
(b) cover every ``outputs`` prefix the playbook step needs to be markable
``completed`` (the D4 -> FR-1106 contract). Synthetic result dicts mirror the
certified modules' real shapes; the integration tests re-validate against live
R output.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from generator import build_golden
from integration_study import build_integration_study
from stages_util import playbook, stage_context

from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig
from burhan.core.policy import Policy
from burhan.prep.py_impl.pipeline import run_prep
from burhan.results.store import ResultsStore
from burhan.stages import context, serialize

REPO = Path(__file__).resolve().parents[3]


def _policy() -> Policy:
    return Policy.load(REPO / "policy" / "decision_policy.template.yaml", mode="certification")


def _covers(store: ResultsStore, step: str) -> None:
    """Every outputs prefix of ``step`` has at least one matching store row."""
    for prefix in playbook().outputs(step):
        assert any(True for _ in store.iter(prefix)), f"{step}: no row for {prefix}"


def _write(tmp_path: Path, stage: str, rows: list[dict[str, Any]]) -> ResultsStore:
    ctx = stage_context(tmp_path, stage=stage)
    context.store_rows(ctx, rows)
    return ctx.store


# -- synthetic module results (mirror the certified shapes) -------------------

_MONTECARLO = {
    "replications": 40,
    "n": 300,
    "converged": 40,
    "power": {"CUL~RES": 0.9, "INT~CUL": 0.95},
}
_VIF = {"composites": [{"composite": "RS1", "r_squared": 0.4, "vif": 1.67, "tolerance": 0.6}]}
_ESTIMATOR = {"estimator": "mlr", "basis": "covariance", "rule_id": "estimator.robust_trigger"}
_MEASUREMENT = {
    "approach": "first_order_only",
    "first_order": {
        "loadings": [
            {"construct": "RES", "item": "RS1", "est": 0.44, "std": 0.72, "se": 0.07, "p": 0.0},
            {"construct": "CUL", "item": "CU1", "est": 0.50, "std": 0.75, "se": 0.06, "p": 0.0},
        ],
        "reliability": [
            {"construct": "RES", "alpha": 0.82, "cr": 0.83, "ave": 0.55},
            {"construct": "CUL", "alpha": 0.80, "cr": 0.81, "ave": 0.54},
        ],
    },
    "validity": {
        "htmt": {
            "pairs": [{"a": "RES", "b": "CUL", "value": 0.20, "band": "pass"}],
            "verdict": "pass",
        }
    },
}
_DELETION = {
    "mode": "recommendation",
    "candidates": [{"item": "IN4"}],
    "deletions": [],
    "skipped": [],
}
_STRUCTURAL = {
    "fit": {
        "chisq": 51.4,
        "cfi": 1.0,
        "tli": 1.0,
        "rmsea": 0.0,
        "srmr": 0.061,
        "df": 52,
        "pvalue": 0.5,
    },
    "paths": [{"lhs": "CUL", "rhs": "RES", "est": 0.51, "std": 0.25, "se": 0.16, "p": 0.0}],
    "r_squared": [{"construct": "CUL", "r2": 0.06}],
}
_BLOCK = {"est": 0.27, "se": 0.1, "ci_low": 0.1, "ci_high": 0.4, "p": 0.0}
_EFFECTS = {
    "bootstrap": {"ci_level": 0.95, "resamples": 40, "completed": 40, "ci_type": "bca"},
    "paths": [
        {"rhs": "RES", "lhs": "CUL", "est": 0.5, "se": 0.1, "ci_low": 0.3, "ci_high": 0.7, "p": 0.0}
    ],
    "effects": [
        {
            "hypothesis": "H3",
            "from": "RES",
            "to": "INT",
            "via": ["CUL"],
            "direct": None,
            "indirect": _BLOCK,
            "total": _BLOCK,
            "classification": "indirect_only",
        }
    ],
}
_ALTERNATIVES = {
    "alternatives": [
        {"id": "reversed_paths", "delta_aic": 0.0, "delta_bic": 0.0, "preferred": False}
    ],
    "n": 300,
    "flagged": True,
}
_ACHIEVED = {"value": 0.94, "df": 52, "n": 300, "floor": 0.8, "flagged": False}


def test_power_rows_cover_pb01(tmp_path: Path) -> None:
    config = validate_and_build(StudyConfig, build_golden(11, with_defects=False).config)
    rows = serialize.power_rows(config, n=300, playbook=playbook(), montecarlo=_MONTECARLO)
    _covers(_write(tmp_path, "power", rows), "PB-01")


def test_prep_rows_cover_pb02_03_04(tmp_path: Path) -> None:
    study = build_integration_study(20260705, n=40)
    config = validate_and_build(StudyConfig, study.config)
    with tempfile.TemporaryDirectory() as td:
        prep = run_prep(study.write(Path(td)), config, _policy())
    store = _write(tmp_path, "prep", serialize.prep_rows(prep))
    for step in ("PB-02", "PB-03", "PB-04"):
        _covers(store, step)


def test_assumptions_rows_cover_pb05_06_07(tmp_path: Path) -> None:
    study = build_integration_study(20260705, n=40)
    config = validate_and_build(StudyConfig, study.config)
    with tempfile.TemporaryDirectory() as td:
        prep = run_prep(study.write(Path(td)), config, _policy())
    rows = serialize.assumptions_rows(
        prep.frame, playbook=playbook(), vif=_VIF, estimator=_ESTIMATOR
    )
    store = _write(tmp_path, "assumptions", rows)
    for step in ("PB-05", "PB-06", "PB-07"):
        _covers(store, step)


def test_measurement_rows_cover_pb08_09_10_11_13(tmp_path: Path) -> None:
    rows = serialize.measurement_rows(_MEASUREMENT, _DELETION)
    store = _write(tmp_path, "measurement", rows)
    for step in ("PB-08", "PB-09", "PB-10", "PB-11", "PB-13"):
        _covers(store, step)


def test_structural_rows_cover_pb15_16(tmp_path: Path) -> None:
    store = _write(tmp_path, "structural", serialize.structural_rows(_STRUCTURAL))
    for step in ("PB-15", "PB-16"):
        _covers(store, step)


def test_effects_rows_cover_pb17(tmp_path: Path) -> None:
    _covers(_write(tmp_path, "effects", serialize.effects_rows(_EFFECTS)), "PB-17")


def test_robustness_rows_cover_pb18_19(tmp_path: Path) -> None:
    rows = serialize.robustness_rows(_ALTERNATIVES, _ACHIEVED)
    store = _write(tmp_path, "robustness", rows)
    for step in ("PB-18", "PB-19"):
        _covers(store, step)


def test_structural_path_id_uses_arrow_grammar(tmp_path: Path) -> None:
    store = _write(tmp_path, "structural", serialize.structural_rows(_STRUCTURAL))
    assert store.resolve("structural.path.RES->CUL").value == 0.51
