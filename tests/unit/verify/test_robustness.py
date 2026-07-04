"""AT-M12-1 + FR-402: alternative models and achieved power (PB-18/19).

The canonical alternative reverses the declared direct paths; each
alternative is estimated through the structural worker and compared on
fit plus information-criterion deltas computed from chi-square and free
parameters on the same data (Delta-AIC = Delta-chisq + 2*Delta-k;
Delta-BIC = Delta-chisq + ln(N)*Delta-k). Canned workers assert the
call sequence and arithmetic; thresholds come from PB-18/19.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

import pytest
from verify_util import playbook

from burhan.core.errors import IntegrityHalt
from burhan.stats.robustness import (
    achieved_power_report,
    alternative_floor,
    reversed_alternative,
    robustness_store_rows,
    run_alternatives,
)

# reuse the structural fixtures — the benchmark config declares
# F1 -> F3 <- F2, F3 -> F4
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stats_structural"))
from structural_util import benchmark_config, benchmark_frame  # noqa: E402


class _SequenceWorker:
    def __init__(self, results: list[dict[str, Any]]) -> None:
        self._results = list(results)
        self.calls: list[dict[str, Any]] = []

    def call(self, *args: object, **kwargs: object) -> dict[str, Any]:
        payload = args[1] if len(args) > 1 else kwargs.get("payload")
        assert isinstance(payload, dict)
        self.calls.append(payload)
        if not self._results:
            raise AssertionError("SequenceWorker exhausted")
        return self._results.pop(0)


def _structural_result(chisq: float, nfree: int, pairs: list[tuple[str, str]]) -> dict[str, Any]:
    return {
        "carrier": None,
        "model": {"syntax": "\n".join(f"{lhs} ~ {rhs}" for lhs, rhs in pairs), "nfree": nfree},
        "fit": {
            "chisq": chisq,
            "df": 50,
            "pvalue": 0.33,
            "cfi": 0.99,
            "tli": 0.99,
            "rmsea": 0.02,
            "rmsea_ci_lower": 0.0,
            "rmsea_ci_upper": 0.04,
            "srmr": 0.03,
        },
        "paths": [
            {"lhs": lhs, "rhs": rhs, "est": 0.5, "std": 0.5, "se": 0.05, "p": 0.001}
            for lhs, rhs in pairs
        ],
        "r_squared": [
            {"construct": construct, "r2": 0.4} for construct in sorted({lhs for lhs, _ in pairs})
        ],
    }


_RETAINED_PAIRS = [("F3", "F1"), ("F3", "F2"), ("F4", "F3")]
_REVERSED_PAIRS = [("F1", "F3"), ("F2", "F3"), ("F3", "F4")]


def test_reversed_alternative_swaps_directions() -> None:
    alternative = reversed_alternative(benchmark_config())
    hypotheses = {(h.from_, h.to) for h in alternative.hypotheses}
    assert hypotheses == {("F3", "F1"), ("F3", "F2"), ("F4", "F3")}
    assert all(h.effect == "direct" for h in alternative.hypotheses)


def test_alternatives_compared_on_fit_and_information_criteria(tmp_path: Path) -> None:
    # Retained chisq 53.7 with k=41; reversed alternative chisq 80.0 with
    # k=41: Delta-AIC = 26.3, Delta-BIC = 26.3 (equal k). Alternative is
    # NOT preferred.
    worker = _SequenceWorker(
        [
            _structural_result(53.7, 41, _RETAINED_PAIRS),
            _structural_result(80.0, 41, _REVERSED_PAIRS),
        ]
    )
    report = run_alternatives(
        benchmark_frame(),
        benchmark_config(),
        playbook=playbook(),
        rworker=worker,  # type: ignore[arg-type]
        run_dir=tmp_path,
        call_id="alt",
    )
    assert len(worker.calls) == 2
    retained_pairs = {(r["lhs"], r["rhs"]) for r in worker.calls[0]["regressions"]}
    reversed_pairs = {(r["lhs"], r["rhs"]) for r in worker.calls[1]["regressions"]}
    assert retained_pairs == set(_RETAINED_PAIRS)
    assert reversed_pairs == set(_REVERSED_PAIRS)
    (alternative,) = report["alternatives"]
    assert alternative["id"] == "reversed_paths"
    assert round(alternative["delta_aic"], 6) == 26.3
    assert round(alternative["delta_bic"], 6) == 26.3
    assert alternative["preferred"] is False
    assert report["flagged"] is False
    assert report["retained"]["fit"]["chisq"] == 53.7


def test_preferred_alternative_flags(tmp_path: Path) -> None:
    # Alternative fits BETTER (lower chisq, same k) -> negative deltas ->
    # preferred -> PB-18 failure_action flag.
    worker = _SequenceWorker(
        [
            _structural_result(80.0, 41, _RETAINED_PAIRS),
            _structural_result(53.7, 41, _REVERSED_PAIRS),
        ]
    )
    report = run_alternatives(
        benchmark_frame(),
        benchmark_config(),
        playbook=playbook(),
        rworker=worker,  # type: ignore[arg-type]
        run_dir=tmp_path,
        call_id="alt-pref",
    )
    (alternative,) = report["alternatives"]
    assert alternative["preferred"] is True
    assert report["flagged"] is True


def test_bic_uses_ln_n_when_k_differs(tmp_path: Path) -> None:
    worker = _SequenceWorker(
        [
            _structural_result(53.7, 41, _RETAINED_PAIRS),
            _structural_result(60.0, 43, _REVERSED_PAIRS),
        ]
    )
    report = run_alternatives(
        benchmark_frame(),
        benchmark_config(),
        playbook=playbook(),
        rworker=worker,  # type: ignore[arg-type]
        run_dir=tmp_path,
        call_id="alt-bic",
    )
    (alternative,) = report["alternatives"]
    n = 500  # ex5.11 complete cases
    assert round(alternative["delta_aic"], 6) == round(6.3 + 2 * 2, 6)
    assert round(alternative["delta_bic"], 6) == round(6.3 + math.log(n) * 2, 6)
    assert report["n"] == n


def test_alternative_floor_from_playbook() -> None:
    assert alternative_floor(playbook()) == 1


def test_doctored_playbook_floor_halts() -> None:
    class DoctoredPlaybook:
        @staticmethod
        def criteria(step_id: str) -> list[dict[str, Any]]:
            if step_id == "PB-18":
                return [{"name": "alternative_required", "value": "one"}]
            return []

    with pytest.raises(IntegrityHalt) as excinfo:
        alternative_floor(DoctoredPlaybook())  # type: ignore[arg-type]
    assert "alternative" in excinfo.value.message


def test_achieved_power_report_flags_below_floor() -> None:
    # df = 50 (ex5.11 model), tiny N -> low close-fit power -> flagged.
    low = achieved_power_report(benchmark_config(), n=60, playbook=playbook())
    assert low["floor"] == 0.80
    assert 0.0 < low["value"] < 0.80
    assert low["flagged"] is True
    high = achieved_power_report(benchmark_config(), n=2000, playbook=playbook())
    assert high["value"] > 0.80
    assert high["flagged"] is False


def test_doctored_pb19_floor_halts() -> None:
    class DoctoredPlaybook:
        @staticmethod
        def criteria(step_id: str) -> list[dict[str, Any]]:
            if step_id == "PB-19":
                return [{"name": "achieved_power_report", "value": "high"}]
            return []

    with pytest.raises(IntegrityHalt) as excinfo:
        achieved_power_report(benchmark_config(), n=200, playbook=DoctoredPlaybook())  # type: ignore[arg-type]
    assert "achieved power" in excinfo.value.message


def test_floors_skip_preceding_unrelated_criteria() -> None:
    class DoctoredPlaybook:
        @staticmethod
        def criteria(step_id: str) -> list[dict[str, Any]]:
            if step_id == "PB-18":
                return [{"name": "other", "value": 9}, {"name": "alternative_required", "value": 2}]
            if step_id == "PB-19":
                return [
                    {"name": "other", "value": 9},
                    {"name": "achieved_power_report", "value": 0.85},
                ]
            return []

    from burhan.stats.robustness import power_floor

    assert alternative_floor(DoctoredPlaybook()) == 2  # type: ignore[arg-type]
    assert power_floor(DoctoredPlaybook()) == 0.85  # type: ignore[arg-type]


def _indirect_only_config() -> Any:
    from burhan.core.artifacts.loader import validate_and_build
    from burhan.core.artifacts.models import StudyConfig

    data = benchmark_config().model_dump(mode="python", exclude_none=True, by_alias=True)
    data["hypotheses"] = [
        {"id": "H1", "effect": "indirect", "from": "F1", "to": "F4", "sign": "positive"}
    ]
    return validate_and_build(StudyConfig, data)


def test_reversed_alternative_without_direct_paths_halts() -> None:
    with pytest.raises(IntegrityHalt) as excinfo:
        reversed_alternative(_indirect_only_config())
    assert "no direct path to reverse" in excinfo.value.message


def test_reversed_alternative_drops_non_direct_hypotheses() -> None:
    from burhan.core.artifacts.loader import validate_and_build
    from burhan.core.artifacts.models import StudyConfig

    data = benchmark_config().model_dump(mode="python", exclude_none=True, by_alias=True)
    data["hypotheses"].append(
        {"id": "H4", "effect": "indirect", "from": "F1", "to": "F4", "sign": "positive"}
    )
    config = validate_and_build(StudyConfig, data)
    alternative = reversed_alternative(config)
    assert len(alternative.hypotheses) == 3
    assert all(h.effect == "direct" for h in alternative.hypotheses)


def test_fewer_alternatives_than_floor_halts(tmp_path: Path) -> None:
    with pytest.raises(IntegrityHalt) as excinfo:
        run_alternatives(
            benchmark_frame(),
            benchmark_config(),
            playbook=playbook(),
            rworker=_SequenceWorker([]),  # type: ignore[arg-type]
            run_dir=tmp_path,
            call_id="alt-none",
            alternatives=[],
        )
    assert "PB-18 floor" in excinfo.value.message


def test_store_rows_are_writable_payloads(tmp_path: Path) -> None:
    worker = _SequenceWorker(
        [
            _structural_result(53.7, 41, _RETAINED_PAIRS),
            _structural_result(80.0, 41, _REVERSED_PAIRS),
        ]
    )
    report = run_alternatives(
        benchmark_frame(),
        benchmark_config(),
        playbook=playbook(),
        rworker=worker,  # type: ignore[arg-type]
        run_dir=tmp_path,
        call_id="alt-store",
    )
    power = achieved_power_report(benchmark_config(), n=500, playbook=playbook())
    rows = robustness_store_rows(report, power)
    ids = {row["id"] for row in rows}
    assert "robustness.alternatives.reversed_paths.delta_aic" in ids
    assert "robustness.alternatives.reversed_paths.delta_bic" in ids
    assert "robustness.achieved_power" in ids
    for row in rows:
        assert not {"schema_version", "created", "hash"} & set(row)
        assert row["stage"] == "robustness"
        assert row["id"].split(".", 1)[0] == "robustness"

    from verify_util import FixedClock

    from burhan.results.store import ResultsStore

    store = ResultsStore(tmp_path / "results", FixedClock())
    for row in rows:
        store.write(row)
    assert store.resolve("robustness.achieved_power").playbook_step == "PB-19"
