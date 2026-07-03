"""Guard paths for the measurement module — every halt is typed."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from measurement_util import two_construct_config, validity_frame

from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig
from burhan.core.errors import IntegrityHalt
from burhan.core.playbook import Playbook
from burhan.core.policy import Policy
from burhan.stats.measurement import (
    build_measurement_payload,
    evaluate_cmb,
    measurement_bands,
    run_measurement,
)

REPO = Path(__file__).resolve().parents[3]


def _playbook() -> Playbook:
    return Playbook.load(REPO / "playbooks" / "CB_SEM_PLAYBOOK_v1.0.yaml", mode="certification")


def _policy() -> Policy:
    return Policy.load(REPO / "policy" / "decision_policy.template.yaml", mode="certification")


def _config(mutate: Any = None) -> StudyConfig:
    data = two_construct_config()
    if mutate is not None:
        mutate(data)
    return validate_and_build(StudyConfig, data)


class _DoctoredPlaybook:
    def __init__(self, criteria: dict[str, list[dict[str, Any]]]) -> None:
        self._criteria = criteria

    def criteria(self, step_id: str) -> list[dict[str, Any]]:
        return self._criteria.get(step_id, [])


_GOOD_PB09 = {
    "name": "loading_target",
    "value": 0.708,
    "rule": ">= 0.708 target (AVE logic); 0.70–0.708 borderline-acceptable",
}
_GOOD_PB10 = [
    {"name": "alpha_floor", "value": 0.70},
    {"name": "cr_floor", "value": 0.70},
    {"name": "ave_floor", "value": 0.50},
]
_GOOD_PB11 = {
    "name": "htmt_ceiling",
    "value": 0.85,
    "rule": "HTMT < 0.85; 0.85–0.90 flagged; > 0.90 fails",
}
_GOOD_PB12 = {"name": "harman_screen", "value": 0.50}


def test_missing_criterion_halts() -> None:
    playbook = _DoctoredPlaybook({"PB-09": []})
    with pytest.raises(IntegrityHalt) as excinfo:
        measurement_bands(playbook)  # type: ignore[arg-type]
    assert "loading_target" in excinfo.value.message


def test_unparseable_borderline_rule_halts() -> None:
    playbook = _DoctoredPlaybook(
        {
            "PB-09": [{"name": "loading_target", "value": 0.708, "rule": "be strict"}],
            "PB-10": _GOOD_PB10,
            "PB-11": [_GOOD_PB11],
            "PB-12": [_GOOD_PB12],
        }
    )
    with pytest.raises(IntegrityHalt) as excinfo:
        measurement_bands(playbook)  # type: ignore[arg-type]
    assert "borderline" in excinfo.value.message


def test_unparseable_htmt_fail_bound_halts() -> None:
    playbook = _DoctoredPlaybook(
        {
            "PB-09": [_GOOD_PB09],
            "PB-10": _GOOD_PB10,
            "PB-11": [{"name": "htmt_ceiling", "value": 0.85, "rule": "keep it low"}],
            "PB-12": [_GOOD_PB12],
        }
    )
    with pytest.raises(IntegrityHalt) as excinfo:
        measurement_bands(playbook)  # type: ignore[arg-type]
    assert "fail bound" in excinfo.value.message


def test_frame_missing_designed_items_halts() -> None:
    frame = validity_frame().drop(columns=["B4"])
    with pytest.raises(IntegrityHalt) as excinfo:
        build_measurement_payload(frame, _config(), approach=None)
    assert "lacks designed items" in excinfo.value.message


def test_too_few_complete_cases_halt() -> None:
    frame = validity_frame().head(6)
    with pytest.raises(IntegrityHalt) as excinfo:
        build_measurement_payload(frame, _config(), approach=None)
    assert "complete cases" in excinfo.value.message


def test_multiple_second_order_constructs_halt() -> None:
    def add_two_second_orders(data: dict[str, Any]) -> None:
        for code in ("S1", "S2"):
            data["constructs"].append(
                {
                    "code": code,
                    "name": code,
                    "level": "second_order",
                    "measurement": "reflective",
                    "components": ["FA", "FB"],
                }
            )
        data["higher_order"] = {
            "approach": "repeated_indicator",
            "structural_carry": "full_hierarchy",
        }

    with pytest.raises(IntegrityHalt) as excinfo:
        build_measurement_payload(validity_frame(), _config(add_two_second_orders), approach=None)
    assert "one second-order" in excinfo.value.message


class _CannedWorker:
    def __init__(self, result: object) -> None:
        self._result = result

    def call(self, *args: object, **kwargs: object) -> object:
        return self._result


def _run_with(result: object, tmp_path: Path) -> None:
    run_measurement(
        validity_frame(),
        _config(),
        policy=_policy(),
        playbook=_playbook(),
        rworker=_CannedWorker(result),  # type: ignore[arg-type]
        run_dir=tmp_path,
        call_id="guard",
    )


_BASE_OK: dict[str, Any] = {
    "approach": "first_order_only",
    "first_order": {"loadings": [], "reliability": []},
    "second_order": None,
    "fit": {"chisq": 1.0, "df": 1},
    "validity": {"latent_correlations": [], "htmt": []},
}


@pytest.mark.parametrize(
    ("mutation", "named"),
    [
        (lambda r: r.update(first_order={"loadings": "many", "reliability": []}), "loadings"),
        (
            lambda r: r.update(
                first_order={
                    "loadings": [{"construct": "FA", "item": "A1"}],
                    "reliability": [],
                }
            ),
            "required fields",
        ),
        (
            lambda r: r.update(
                first_order={
                    "loadings": [
                        {
                            "construct": "FA",
                            "item": "A1",
                            "est": "big",
                            "std": 0.7,
                            "se": 0.05,
                        }
                    ],
                    "reliability": [],
                }
            ),
            "nonnumeric est",
        ),
        (
            lambda r: r.update(
                first_order={
                    "loadings": [],
                    "reliability": [{"construct": "FA", "alpha": 1.4, "cr": 0.8, "ave": 0.5}],
                }
            ),
            "out of range",
        ),
        (lambda r: r.update(fit={"chisq": "small"}), "chisq"),
        (
            lambda r: r.update(
                validity={
                    "latent_correlations": [{"a": "FA", "b": "FB", "value": "high"}],
                    "htmt": [],
                }
            ),
            "nonnumeric value",
        ),
    ],
)
def test_malformed_worker_blocks_halt_typed(tmp_path: Path, mutation: Any, named: str) -> None:
    result: dict[str, Any] = {
        key: (dict(value) if isinstance(value, dict) else value) for key, value in _BASE_OK.items()
    }
    mutation(result)
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert named in excinfo.value.message


def test_non_mapping_worker_result_halts(tmp_path: Path) -> None:
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(["not", "a", "mapping"], tmp_path)
    assert "measurement" in excinfo.value.message


def test_invalid_second_order_stage_halts(tmp_path: Path) -> None:
    def add_second_order(data: dict[str, Any]) -> None:
        data["constructs"].append(
            {
                "code": "SO",
                "name": "Second order",
                "level": "second_order",
                "measurement": "reflective",
                "components": ["FA", "FB"],
            }
        )
        data["higher_order"] = {
            "approach": "repeated_indicator",
            "structural_carry": "full_hierarchy",
        }

    result = {
        **_BASE_OK,
        "second_order": {
            "loadings": [],
            "reliability": {"construct": "SO", "cr_l2": 0.8, "omega_l1": 0.7},
            "stage": 7,
        },
    }
    with pytest.raises(IntegrityHalt) as excinfo:
        run_measurement(
            validity_frame(),
            _config(add_second_order),
            policy=_policy(),
            playbook=_playbook(),
            rworker=_CannedWorker(result),  # type: ignore[arg-type]
            run_dir=tmp_path,
            call_id="guard-stage",
        )
    assert "stage" in excinfo.value.message


def test_harman_share_out_of_range_halts() -> None:
    with pytest.raises(IntegrityHalt) as excinfo:
        evaluate_cmb({"harman": {"single_factor_share": 1.7}}, playbook=_playbook())
    assert "out of range" in excinfo.value.message


def test_second_order_without_declared_approach_halts() -> None:
    def add_second_order_without_higher_order(data: dict[str, Any]) -> None:
        data["constructs"].append(
            {
                "code": "SO",
                "name": "Second order",
                "level": "second_order",
                "measurement": "reflective",
                "components": ["FA", "FB"],
            }
        )

    with pytest.raises(IntegrityHalt) as excinfo:
        build_measurement_payload(
            validity_frame(), _config(add_second_order_without_higher_order), approach=None
        )
    assert "higher-order approach" in excinfo.value.message


def test_nonnumeric_p_in_loading_entry_halts(tmp_path: Path) -> None:
    result: dict[str, Any] = {
        **_BASE_OK,
        "first_order": {
            "loadings": [
                {
                    "construct": "FA",
                    "item": "A1",
                    "est": 1.0,
                    "std": 0.7,
                    "se": 0.05,
                    "p": "tiny",
                }
            ],
            "reliability": [],
        },
    }
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert "nonnumeric p" in excinfo.value.message


def test_malformed_l2_reliability_halts(tmp_path: Path) -> None:
    def add_second_order(data: dict[str, Any]) -> None:
        data["constructs"].append(
            {
                "code": "SO",
                "name": "Second order",
                "level": "second_order",
                "measurement": "reflective",
                "components": ["FA", "FB"],
            }
        )
        data["higher_order"] = {
            "approach": "repeated_indicator",
            "structural_carry": "full_hierarchy",
        }

    result = {
        **_BASE_OK,
        "second_order": {
            "loadings": [],
            "reliability": {"construct": "SO", "cr_l2": "high", "omega_l1": 0.7},
            "stage": 1,
        },
    }
    with pytest.raises(IntegrityHalt) as excinfo:
        run_measurement(
            validity_frame(),
            _config(add_second_order),
            policy=_policy(),
            playbook=_playbook(),
            rworker=_CannedWorker(result),  # type: ignore[arg-type]
            run_dir=tmp_path,
            call_id="guard-l2",
        )
    assert "second_order reliability" in excinfo.value.message


@pytest.mark.parametrize("field", ["cr_l2", "omega_l1"])
@pytest.mark.parametrize(
    "bad_value",
    [-0.1, 0.0, 1.7, True, None, "high"],
    ids=["negative", "zero", "above_one", "boolean", "null", "nonnumeric"],
)
def test_out_of_range_l2_reliability_halts(tmp_path: Path, field: str, bad_value: object) -> None:
    # Reliability is a proportion: both L2 fields must be real numbers in
    # (0, 1]. Impossible values from the worker halt typed, naming the field.
    def add_second_order(data: dict[str, Any]) -> None:
        data["constructs"].append(
            {
                "code": "SO",
                "name": "Second order",
                "level": "second_order",
                "measurement": "reflective",
                "components": ["FA", "FB"],
            }
        )
        data["higher_order"] = {
            "approach": "repeated_indicator",
            "structural_carry": "full_hierarchy",
        }

    reliability: dict[str, Any] = {"construct": "SO", "cr_l2": 0.7, "omega_l1": 0.7}
    reliability[field] = bad_value
    result = {
        **_BASE_OK,
        "second_order": {"loadings": [], "reliability": reliability, "stage": 1},
    }
    with pytest.raises(IntegrityHalt) as excinfo:
        run_measurement(
            validity_frame(),
            _config(add_second_order),
            policy=_policy(),
            playbook=_playbook(),
            rworker=_CannedWorker(result),  # type: ignore[arg-type]
            run_dir=tmp_path,
            call_id="guard-l2-range",
        )
    assert "second_order reliability" in excinfo.value.message
    assert excinfo.value.details == {"field": field}


def test_fornell_larcker_fails_when_shared_variance_exceeds_ave(tmp_path: Path) -> None:
    # Negative control for the F–L rule itself: AVE .55 against a latent
    # correlation of .80 (shared variance .64) must fail the criterion.
    result: dict[str, Any] = {
        **_BASE_OK,
        "first_order": {
            "loadings": [],
            "reliability": [
                {"construct": "FA", "alpha": 0.8, "cr": 0.8, "ave": 0.55},
                {"construct": "FB", "alpha": 0.8, "cr": 0.8, "ave": 0.58},
            ],
        },
        "validity": {
            "latent_correlations": [{"a": "FA", "b": "FB", "value": 0.80}],
            "htmt": [{"a": "FA", "b": "FB", "value": 0.82}],
        },
    }
    report = run_measurement(
        validity_frame(),
        _config(),
        policy=_policy(),
        playbook=_playbook(),
        rworker=_CannedWorker(result),  # type: ignore[arg-type]
        run_dir=tmp_path,
        call_id="guard-fl-fail",
    )
    fl = report["validity"]["fornell_larcker"]
    assert fl["pass"] is False
    per_construct = {e["construct"]: e for e in fl["constructs"]}
    assert per_construct["FA"]["pass"] is False  # .55 < .64
    assert per_construct["FA"]["max_shared_variance"] == pytest.approx(0.64)


def test_deletion_candidate_band_assigned_below_borderline(tmp_path: Path) -> None:
    result: dict[str, Any] = {
        **_BASE_OK,
        "first_order": {
            "loadings": [
                {"construct": "FA", "item": "A1", "est": 0.4, "std": 0.42, "se": 0.05, "p": 0.001}
            ],
            "reliability": [{"construct": "FA", "alpha": 0.8, "cr": 0.8, "ave": 0.55}],
        },
    }
    report = run_measurement(
        validity_frame(),
        _config(),
        policy=_policy(),
        playbook=_playbook(),
        rworker=_CannedWorker(result),  # type: ignore[arg-type]
        run_dir=tmp_path,
        call_id="guard-band",
    )
    assert report["first_order"]["loadings"][0]["band"] == "deletion_candidate"
