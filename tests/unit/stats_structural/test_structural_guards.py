"""Guard paths for the structural module — every halt is typed.

Canned workers prove the engine validates every result block, that band
evaluation is report-only by construction (a failing fit produces a
report, never a re-fit or a mutated model), and that PB-15 thresholds
come from the governed playbook, never constants.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from structural_util import benchmark_config, benchmark_frame, playbook

from burhan.core.errors import IntegrityHalt
from burhan.stats.structural import evaluate_fit_bands, fit_bands, run_structural


class _CannedWorker:
    def __init__(self, result: object) -> None:
        self._result = result
        self.calls: list[dict[str, Any]] = []

    def call(self, *args: object, **kwargs: object) -> object:
        payload = args[1] if len(args) > 1 else kwargs.get("payload")
        assert isinstance(payload, dict)
        self.calls.append(payload)
        return self._result


def _good_fit() -> dict[str, Any]:
    return {
        "chisq": 53.7,
        "df": 50,
        "pvalue": 0.33,
        "cfi": 0.997,
        "tli": 0.997,
        "rmsea": 0.012,
        "rmsea_ci_lower": 0.0,
        "rmsea_ci_upper": 0.032,
        "srmr": 0.027,
    }


def _result(fit: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "carrier": None,
        "model": {"syntax": "F3 ~ F1 + F2\nF4 ~ F3", "nfree": 41},
        "fit": fit if fit is not None else _good_fit(),
        "paths": [
            {"lhs": "F3", "rhs": "F1", "est": 0.563, "std": 0.5, "se": 0.07, "p": 0.001},
            {"lhs": "F3", "rhs": "F2", "est": 0.790, "std": 0.6, "se": 0.09, "p": 0.001},
            {"lhs": "F4", "rhs": "F3", "est": 0.473, "std": 0.5, "se": 0.06, "p": 0.001},
        ],
        "r_squared": [
            {"construct": "F3", "r2": 0.59},
            {"construct": "F4", "r2": 0.35},
        ],
    }


def _run_with(result: object, tmp_path: Path) -> dict[str, Any]:
    return run_structural(
        benchmark_frame(),
        benchmark_config(),
        playbook=playbook(),
        rworker=_CannedWorker(result),  # type: ignore[arg-type]
        run_dir=tmp_path,
        call_id="guard-sem",
    )


def test_failing_fit_is_reported_never_refit(tmp_path: Path) -> None:
    # AT-M11-1 report-only: a fit failing every band still returns a
    # complete report from exactly ONE worker call — no code path feeds
    # the evaluation back into the model.
    bad = dict(_good_fit(), chisq=400.0, cfi=0.5, tli=0.5, rmsea=0.2, srmr=0.2)
    worker = _CannedWorker(_result(bad))
    report = run_structural(
        benchmark_frame(),
        benchmark_config(),
        playbook=playbook(),
        rworker=worker,  # type: ignore[arg-type]
        run_dir=tmp_path,
        call_id="guard-bad-fit",
    )
    assert len(worker.calls) == 1
    verdicts = {e["criterion"]: e["verdict"] for e in report["band_evaluation"]["entries"]}
    assert verdicts == {
        "normed_chisq": "fail",
        "cfi_floor": "fail",
        "tli_floor": "fail",
        "rmsea_ceiling": "fail",
        "srmr_ceiling": "fail",
    }
    assert report["band_evaluation"]["action"] == "report"
    assert report["model"] == {"syntax": "F3 ~ F1 + F2\nF4 ~ F3", "nfree": 41}
    assert "error_covariances" not in worker.calls[0]


def test_saturated_model_normed_chisq_not_applicable(tmp_path: Path) -> None:
    saturated = dict(
        _good_fit(), chisq=0.0, df=0, pvalue=None, cfi=1.0, tli=1.0, rmsea=0.0, srmr=0.0
    )
    report = _run_with(_result(saturated), tmp_path)
    entries = {e["criterion"]: e for e in report["band_evaluation"]["entries"]}
    assert entries["normed_chisq"]["verdict"] == "not_applicable"
    assert entries["normed_chisq"]["observed"] is None


def test_null_pvalue_with_positive_df_halts(tmp_path: Path) -> None:
    broken = dict(_good_fit(), pvalue=None)
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(_result(broken), tmp_path)
    assert "pvalue" in excinfo.value.message


@pytest.mark.parametrize(
    "key",
    ["chisq", "df", "cfi", "tli", "rmsea", "rmsea_ci_lower", "rmsea_ci_upper", "srmr"],
)
def test_missing_or_nonnumeric_fit_field_halts(tmp_path: Path, key: str) -> None:
    for bad_value in ("big", None, True):
        fit = dict(_good_fit())
        fit[key] = bad_value
        with pytest.raises(IntegrityHalt) as excinfo:
            _run_with(_result(fit), tmp_path)
        assert key in excinfo.value.message


def test_fractional_df_halts(tmp_path: Path) -> None:
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(_result(dict(_good_fit(), df=49.5)), tmp_path)
    assert "df" in excinfo.value.message


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf")], ids=["nan", "inf"])
def test_nonfinite_df_halts_typed_not_raw(tmp_path: Path, bad_value: float) -> None:
    # REJECT-2: int(NaN/Inf) raises raw ValueError/OverflowError — the
    # guard must prove finiteness before any integer conversion.
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(_result(dict(_good_fit(), df=bad_value)), tmp_path)
    assert "df" in excinfo.value.message


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf")], ids=["nan", "inf"])
def test_nonfinite_nfree_halts_typed_not_raw(tmp_path: Path, bad_value: float) -> None:
    result = _result()
    result["model"] = {"syntax": "F3 ~ F1 + F2\nF4 ~ F3", "nfree": bad_value}
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert "nfree" in excinfo.value.message


@pytest.mark.parametrize(
    ("mutate", "named"),
    [
        (lambda r: r.update(paths="three"), "paths"),
        (lambda r: r.update(paths=[{"lhs": "F3"}]), "paths"),
        (
            lambda r: r.update(
                paths=[{"lhs": "F3", "rhs": "F1", "est": "big", "std": 0.5, "se": 0.1, "p": 0.5}]
            ),
            "paths",
        ),
        (lambda r: r.update(model={"syntax": "", "nfree": 41}), "syntax"),
        (lambda r: r.update(model={"syntax": "F3 ~ F1", "nfree": "many"}), "nfree"),
        (lambda r: r.pop("fit"), "fit"),
    ],
    ids=[
        "paths_not_list",
        "path_missing_fields",
        "path_nonnumeric_est",
        "blank_syntax",
        "nonint_nfree",
        "missing_fit",
    ],
)
def test_malformed_worker_blocks_halt_typed(tmp_path: Path, mutate: Any, named: str) -> None:
    result = _result()
    mutate(result)
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert named in excinfo.value.message


def test_nonmapping_worker_result_halts(tmp_path: Path) -> None:
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(["not", "a", "mapping"], tmp_path)
    assert "structural" in excinfo.value.message


def test_carrier_mismatch_from_worker_halts(tmp_path: Path) -> None:
    # The worker must fit the carrier it was asked for; benchmark config
    # declares none, so a worker inventing one halts.
    result = _result()
    result["carrier"] = "latent_scores"
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert "carrier" in excinfo.value.message


def test_config_without_direct_hypotheses_halts(tmp_path: Path) -> None:
    from structural_util import _base_config  # fixture-internal builder

    items = {"FA": ["A1", "A2", "A3"], "FB": ["B1", "B2", "B3"]}
    constructs: list[dict[str, Any]] = [
        {
            "code": code,
            "name": code,
            "level": "first_order",
            "measurement": "reflective",
            "indicators": list(codes),
        }
        for code, codes in items.items()
    ]
    config = _base_config(
        items,
        constructs,
        [{"id": "H1", "effect": "indirect", "from": "FA", "to": "FB", "sign": "positive"}],
        {"exogenous": ["FA"], "endogenous": ["FB"]},
        None,
    )
    import pandas as pd

    frame = benchmark_frame().iloc[:, :6]
    frame = frame.set_axis(["A1", "A2", "A3", "B1", "B2", "B3"], axis=1)
    assert isinstance(frame, pd.DataFrame)
    with pytest.raises(IntegrityHalt) as excinfo:
        run_structural(
            frame,
            config,
            playbook=playbook(),
            rworker=_CannedWorker(_result()),  # type: ignore[arg-type]
            run_dir=tmp_path,
            call_id="guard-nopaths",
        )
    assert "direct structural path" in excinfo.value.message


def test_hypothesis_naming_unknown_construct_halts(tmp_path: Path) -> None:
    from structural_util import _base_config

    items = {"FA": ["A1", "A2", "A3"], "FB": ["B1", "B2", "B3"]}
    constructs: list[dict[str, Any]] = [
        {
            "code": code,
            "name": code,
            "level": "first_order",
            "measurement": "reflective",
            "indicators": list(codes),
        }
        for code, codes in items.items()
    ]
    config = _base_config(
        items,
        constructs,
        [{"id": "H1", "effect": "direct", "from": "FZ", "to": "FB", "sign": "positive"}],
        {"exogenous": ["FA"], "endogenous": ["FB"]},
        None,
    )
    frame = benchmark_frame().iloc[:, :6]
    frame = frame.set_axis(["A1", "A2", "A3", "B1", "B2", "B3"], axis=1)
    with pytest.raises(IntegrityHalt) as excinfo:
        run_structural(
            frame,
            config,
            playbook=playbook(),
            rworker=_CannedWorker(_result()),  # type: ignore[arg-type]
            run_dir=tmp_path,
            call_id="guard-unknown",
        )
    assert "unknown construct" in excinfo.value.message


@pytest.mark.parametrize(
    "doctor",
    [
        lambda crits: [c for c in crits if c["name"] != "cfi_floor"],
        lambda crits: [dict(c, rule="be strict") if c["name"] == "cfi_floor" else c for c in crits],
        lambda crits: [
            dict(c, rule="keep it low") if c["name"] == "rmsea_ceiling" else c for c in crits
        ],
        lambda crits: [dict(c, value="high") if c["name"] == "srmr_ceiling" else c for c in crits],
    ],
    ids=["missing_criterion", "cfi_good_unparseable", "rmsea_good_unparseable", "nonnumeric_value"],
)
def test_doctored_playbook_halts(doctor: Any) -> None:
    real = playbook()

    class DoctoredPlaybook:
        @staticmethod
        def criteria(step_id: str) -> list[dict[str, Any]]:
            crits = real.criteria(step_id)
            if step_id == "PB-15":
                return doctor([dict(c) for c in crits])
            return crits

        @staticmethod
        def step(step_id: str) -> dict[str, Any]:
            return real.step(step_id)

    with pytest.raises(IntegrityHalt):
        fit_bands(DoctoredPlaybook())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("key", "bad_value"),
    [
        ("chisq", float("nan")),
        ("chisq", -1.0),
        ("cfi", float("nan")),
        ("cfi", 1.2),
        ("cfi", -0.1),
        ("tli", float("nan")),
        ("rmsea", float("inf")),
        ("rmsea", -0.01),
        ("rmsea_ci_lower", -0.1),
        ("rmsea_ci_upper", float("inf")),
        ("srmr", -0.01),
        ("srmr", float("nan")),
        ("pvalue", -0.1),
        ("pvalue", 1.5),
        ("pvalue", float("nan")),
    ],
    ids=lambda v: repr(v),
)
def test_nonfinite_or_out_of_range_fit_halts(tmp_path: Path, key: str, bad_value: float) -> None:
    # REJECT-1 fix 1: NaN, Inf, negative probabilities, and impossible
    # index values are not statistics — they halt typed, naming the field.
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(_result(dict(_good_fit(), **{key: bad_value})), tmp_path)
    assert key in excinfo.value.message


def test_rmsea_ci_out_of_order_halts(tmp_path: Path) -> None:
    broken = dict(_good_fit(), rmsea_ci_lower=0.05, rmsea_ci_upper=0.01)
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(_result(broken), tmp_path)
    assert "rmsea_ci" in excinfo.value.message


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("est", float("inf")),
        ("std", float("nan")),
        ("se", -0.1),
        ("se", float("nan")),
        ("p", 1.5),
        ("p", -0.2),
    ],
    ids=["est_inf", "std_nan", "se_negative", "se_nan", "p_above_one", "p_negative"],
)
def test_nonfinite_or_out_of_range_path_field_halts(
    tmp_path: Path, field: str, bad_value: float
) -> None:
    result = _result()
    result["paths"][0][field] = bad_value
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert field in excinfo.value.message


def test_missing_requested_path_halts(tmp_path: Path) -> None:
    # REJECT-1 fix 2: the worker must return exactly the regressions it
    # was sent — a dropped pair halts, naming what is missing.
    result = _result()
    result["paths"] = result["paths"][:2]
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert "missing" in excinfo.value.message
    assert excinfo.value.details["missing"] == [["F4", "F3"]]


def test_extra_unrequested_path_halts(tmp_path: Path) -> None:
    result = _result()
    result["paths"].append(
        {"lhs": "NOPE", "rhs": "FZ", "est": 0.1, "std": 0.1, "se": 0.1, "p": 0.5}
    )
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert "extra" in excinfo.value.message
    assert excinfo.value.details["extra"] == [["NOPE", "FZ"]]


def test_duplicate_path_halts(tmp_path: Path) -> None:
    result = _result()
    result["paths"].append(dict(result["paths"][0]))
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert "duplicate" in excinfo.value.message


def test_missing_r_squared_block_halts(tmp_path: Path) -> None:
    # REJECT-1 fix 3 (FR-801): R² per endogenous construct is mandatory.
    result = _result()
    result.pop("r_squared")
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert "r_squared" in excinfo.value.message


@pytest.mark.parametrize(
    "entries",
    [
        [{"construct": "F3", "r2": 0.59}],
        [
            {"construct": "F3", "r2": 0.59},
            {"construct": "F4", "r2": 0.35},
            {"construct": "FZ", "r2": 0.1},
        ],
        [{"construct": "F3", "r2": 0.59}, {"construct": "F3", "r2": 0.59}],
        [{"construct": "F3", "r2": 1.2}, {"construct": "F4", "r2": 0.35}],
        [{"construct": "F3", "r2": float("nan")}, {"construct": "F4", "r2": 0.35}],
        [{"construct": "F3", "r2": "high"}, {"construct": "F4", "r2": 0.35}],
        [{"construct": "F3", "r2": -0.05}, {"construct": "F4", "r2": 0.35}],
        ["not-a-mapping", {"construct": "F4", "r2": 0.35}],
    ],
    ids=[
        "missing_endogenous",
        "extra_construct",
        "duplicate_construct",
        "above_one",
        "nan",
        "nonnumeric",
        "negative",
        "nonmapping_entry",
    ],
)
def test_malformed_r_squared_halts(tmp_path: Path, entries: list[Any]) -> None:
    result = _result()
    result["r_squared"] = entries
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert "r_squared" in excinfo.value.message or "r2" in excinfo.value.message


def test_nonnumeric_pvalue_halts(tmp_path: Path) -> None:
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(_result(dict(_good_fit(), pvalue="small")), tmp_path)
    assert "pvalue" in excinfo.value.message


def test_nonnumeric_path_p_halts(tmp_path: Path) -> None:
    result = _result()
    result["paths"][0]["p"] = "tiny"
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert "invalid p" in excinfo.value.message


def test_missing_model_block_halts(tmp_path: Path) -> None:
    result = _result()
    result["model"] = None
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert "model" in excinfo.value.message


def test_doctored_playbook_without_failure_action_halts() -> None:
    real = playbook()

    class DoctoredPlaybook:
        @staticmethod
        def criteria(step_id: str) -> list[dict[str, Any]]:
            return real.criteria(step_id)

        @staticmethod
        def step(step_id: str) -> dict[str, Any]:
            step = dict(real.step(step_id))
            step.pop("failure_action", None)
            return step

    with pytest.raises(IntegrityHalt) as excinfo:
        fit_bands(DoctoredPlaybook())  # type: ignore[arg-type]
    assert "failure_action" in excinfo.value.message


def test_band_evaluation_tiers() -> None:
    bands = fit_bands(playbook())
    good = evaluate_fit_bands(_good_fit(), bands=bands)
    tiers = {e["criterion"]: e["verdict"] for e in good["entries"]}
    assert tiers["cfi_floor"] == "good"
    assert tiers["rmsea_ceiling"] == "good"
    acceptable = evaluate_fit_bands(
        dict(_good_fit(), cfi=0.93, rmsea=0.07, rmsea_ci_upper=0.09), bands=bands
    )
    tiers = {e["criterion"]: e["verdict"] for e in acceptable["entries"]}
    assert tiers["cfi_floor"] == "acceptable"
    assert tiers["rmsea_ceiling"] == "acceptable"
