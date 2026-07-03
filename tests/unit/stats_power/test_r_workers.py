"""R power/assumptions workers: dual-path parity through the real harness.

The R side implements the same published formulas independently; parity
with the Python path at tight tolerance is the FR-501-style independence
evidence for this stage. The worker's ops are ``close_fit`` and
``montecarlo`` (simsem over the renv-locked stack; E-R3 resolved
2026-07-03, exercised in test_montecarlo.py) — any unknown op aborts the
worker and surfaces as a typed halt.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from burhan.core.errors import IntegrityHalt
from burhan.core.rworker import RWorker
from burhan.stats.assumptions import mardia
from burhan.stats.power import close_fit_power

REPO = Path(__file__).resolve().parents[3]
SETOSA = REPO / "tests" / "fixtures" / "known_answers" / "iris_setosa.csv"


def _call(module: str, payload: dict[str, Any], tmp_path: Path, call_id: str) -> dict[str, Any]:
    return RWorker().call(module, payload, call_id=call_id, run_dir=tmp_path, seed=1)


@pytest.mark.parametrize(("df", "n"), [(15, 200), (50, 200), (100, 132), (25, 500)])
def test_close_fit_power_parity_r_vs_python(tmp_path: Path, df: int, n: int) -> None:
    result = _call(
        "power_worker",
        {"op": "close_fit", "df": df, "n": n, "rmsea0": 0.05, "rmsea_a": 0.08, "alpha": 0.05},
        tmp_path,
        f"cf-{df}-{n}",
    )
    assert result["power"] == pytest.approx(close_fit_power(df=df, n=n), abs=1e-9)


def test_close_fit_published_anchor_through_r(tmp_path: Path) -> None:  # AT-M09-1
    result = _call(
        "power_worker",
        {"op": "close_fit", "df": 15, "n": 200, "rmsea0": 0.05, "rmsea_a": 0.08, "alpha": 0.05},
        tmp_path,
        "cf-anchor",
    )
    assert result["power"] == pytest.approx(0.378, abs=0.001)


def test_unknown_op_halts_typed(tmp_path: Path) -> None:
    with pytest.raises(IntegrityHalt) as excinfo:
        _call("power_worker", {"op": "bogus"}, tmp_path, "op-bogus")
    assert "nonzero" in excinfo.value.message
    assert "unimplemented op" in str(excinfo.value.to_report()["details"])


def _diagnostics_payload() -> dict[str, Any]:
    frame = pd.read_csv(SETOSA)
    return {
        "op": "diagnostics",
        "columns": [str(c) for c in frame.columns],
        "cells": [
            [None if math.isnan(v) else float(v) for v in row] for row in frame.to_numpy().tolist()
        ],
        "mahalanobis_p": 0.001,
    }


def test_assumptions_worker_reproduces_published_mardia(tmp_path: Path) -> None:  # AT-M09-3
    result = _call("assumptions_worker", _diagnostics_payload(), tmp_path, "diag-setosa")
    assert result["mardia"]["b1p"] == pytest.approx(3.0797, abs=5e-5)
    assert result["mardia"]["skew_p"] == pytest.approx(0.1772, abs=5e-5)
    assert result["mardia"]["b2p"] == pytest.approx(26.5377, abs=5e-5)
    assert result["mardia"]["kurtosis_p"] == pytest.approx(0.1953, abs=5e-5)


def test_assumptions_parity_r_vs_python(tmp_path: Path) -> None:
    result = _call("assumptions_worker", _diagnostics_payload(), tmp_path, "diag-parity")
    python_result = mardia(pd.read_csv(SETOSA))
    for key in ("b1p", "skew_statistic", "skew_p", "b2p", "kurtosis_z", "kurtosis_p"):
        assert result["mardia"][key] == pytest.approx(python_result[key], abs=1e-9)


def test_r_workers_are_deterministic(tmp_path: Path) -> None:
    first = _call("assumptions_worker", _diagnostics_payload(), tmp_path, "det-1")
    second = _call("assumptions_worker", _diagnostics_payload(), tmp_path, "det-2")
    assert first == second
