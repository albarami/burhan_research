"""FR-902: the semopy independent path against the published anchor.

The engine values are the published ex5.11 estimates (the R engine
reproduces them at printed precision — TC-11a benchmark); semopy fits
the same model live and must agree within the certified parity
tolerance. Doctored engine values exercise the flag and halt bands
end-to-end through run_verification.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from verify_util import parity_map_data, policy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stats_structural"))
from structural_util import benchmark_config, benchmark_frame  # noqa: E402

from burhan.core.errors import IntegrityHalt, VerificationHalt  # noqa: E402
from burhan.verify.independent import (  # noqa: E402
    independent_estimates,
    run_verification,
    semopy_syntax,
)
from burhan.verify.parity import load_parity_map  # noqa: E402

PUBLISHED_PATHS = {("F3", "F1"): 0.563, ("F3", "F2"): 0.790, ("F4", "F3"): 0.473}


def _engine_report(overrides: dict[tuple[str, str], float] | None = None) -> dict[str, Any]:
    values = dict(PUBLISHED_PATHS)
    if overrides:
        values.update(overrides)
    return {
        "paths": [
            {"lhs": lhs, "rhs": rhs, "est": est, "std": 0.5, "se": 0.05, "p": 0.001}
            for (lhs, rhs), est in values.items()
        ]
    }


def test_semopy_agrees_with_published_engine_values() -> None:
    report = run_verification(
        benchmark_frame(),
        benchmark_config(),
        _engine_report(),
        parity_map=load_parity_map(parity_map_data()),
        policy=policy(),
    )
    assert report["scopes_checked"] == ["structural.paths"]
    assert report["flags"] == []
    assert {r["status"] for r in report["results"]} == {"pass"}
    assert len(report["results"]) == 3


def test_doctored_engine_value_flags_with_scope_named() -> None:
    report = run_verification(
        benchmark_frame(),
        benchmark_config(),
        _engine_report({("F3", "F1"): 0.568}),  # ~0.005 off semopy
        parity_map=load_parity_map(parity_map_data()),
        policy=policy(),
    )
    (flag,) = report["flags"]
    assert "structural.paths" in flag
    assert "structural.path.F1->F3" in flag


def test_doctored_engine_value_beyond_halt_multiplier_halts() -> None:
    with pytest.raises(VerificationHalt) as excinfo:
        run_verification(
            benchmark_frame(),
            benchmark_config(),
            _engine_report({("F3", "F1"): 0.60}),  # ~0.037 off = 37x tolerance
            parity_map=load_parity_map(parity_map_data()),
            policy=policy(),
        )
    assert excinfo.value.run_state == "HALTED_VERIFICATION"
    (diff,) = excinfo.value.details["diffs"]
    assert diff["id"] == "structural.path.F1->F3"


def test_engine_path_missing_from_independent_fit_halts() -> None:
    report = _engine_report()
    report["paths"].append({"lhs": "F4", "rhs": "F1", "est": 0.2, "std": 0.2, "se": 0.05, "p": 0.5})
    with pytest.raises(IntegrityHalt) as excinfo:
        run_verification(
            benchmark_frame(),
            benchmark_config(),
            report,
            parity_map=load_parity_map(parity_map_data()),
            policy=policy(),
        )
    assert "independent fit lacks" in excinfo.value.message


def test_independent_estimates_include_loadings() -> None:
    estimates = independent_estimates(benchmark_frame(), benchmark_config())
    # marker convention matches lavaan: y2 on F1 published 1.183
    assert estimates["loadings"][("F1", "y2")] == pytest.approx(1.183, abs=0.01)
    assert set(estimates["paths"]) == set(PUBLISHED_PATHS)


def test_semopy_syntax_guards() -> None:
    config = benchmark_config()
    syntax = semopy_syntax(config)
    assert "F1 =~ y1 + y2 + y3" in syntax
    assert "F3 ~ F1 + F2" in syntax
    assert "F4 ~ F3" in syntax


def _config_with_hypotheses(hypotheses: list[dict[str, Any]]) -> Any:
    from burhan.core.artifacts.loader import validate_and_build
    from burhan.core.artifacts.models import StudyConfig

    data = benchmark_config().model_dump(mode="python", exclude_none=True, by_alias=True)
    data["hypotheses"] = hypotheses
    return validate_and_build(StudyConfig, data)


def test_syntax_unknown_construct_halts() -> None:
    config = _config_with_hypotheses(
        [{"id": "H1", "effect": "direct", "from": "FZ", "to": "F3", "sign": "positive"}]
    )
    with pytest.raises(IntegrityHalt) as excinfo:
        semopy_syntax(config)
    assert "unknown construct" in excinfo.value.message


def test_syntax_without_direct_paths_halts() -> None:
    config = _config_with_hypotheses(
        [{"id": "H1", "effect": "indirect", "from": "F1", "to": "F4", "sign": "positive"}]
    )
    with pytest.raises(IntegrityHalt) as excinfo:
        semopy_syntax(config)
    assert "no direct structural path" in excinfo.value.message


def test_nonfinite_semopy_estimate_halts(monkeypatch: pytest.MonkeyPatch) -> None:
    import pandas as pd

    class _StubModel:
        def __init__(self, desc: str) -> None:
            self.desc = desc

        def fit(self, data: object) -> None:
            return None

        def inspect(self) -> pd.DataFrame:
            return pd.DataFrame([{"lval": "F3", "op": "~", "rval": "F1", "Estimate": float("nan")}])

    import types

    stub = types.ModuleType("semopy")
    stub.Model = _StubModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "semopy", stub)
    with pytest.raises(IntegrityHalt) as excinfo:
        independent_estimates(benchmark_frame(), benchmark_config())
    assert "nonfinite estimate" in excinfo.value.message


def test_frame_missing_items_halts() -> None:
    with pytest.raises(IntegrityHalt) as excinfo:
        independent_estimates(benchmark_frame().drop(columns=["y5"]), benchmark_config())
    assert "lacks designed items" in excinfo.value.message
