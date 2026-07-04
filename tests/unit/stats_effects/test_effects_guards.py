"""Guard paths for the effects stage — every halt is typed.

Canned workers prove the engine validates the bootstrap echo and every
effect block; the payload builder halts on contracts that cannot be
decomposed; bootstrap settings come from the policy layer with typed
validation, never constants.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from effects_util import (
    effect_block,
    mediation_config,
    mediation_frame,
    playbook,
    policy_with,
)

from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig
from burhan.core.errors import IntegrityHalt
from burhan.stats.effects import bootstrap_settings, build_effects_payload, run_effects


class _CannedWorker:
    def __init__(self, result: object) -> None:
        self._result = result
        self.calls: list[dict[str, Any]] = []

    def call(self, *args: object, **kwargs: object) -> object:
        payload = args[1] if len(args) > 1 else kwargs.get("payload")
        assert isinstance(payload, dict)
        self.calls.append(payload)
        return self._result


def _result(resamples: int = 1000) -> dict[str, Any]:
    return {
        "bootstrap": {
            "resamples": resamples,
            "completed": resamples,
            "ci_level": 0.95,
            "ci_type": "bias_corrected",
        },
        "paths": [],
        "effects": [
            {
                "id": "H2",
                "direct": effect_block(0.30, 0.15, 0.45),
                "indirect": effect_block(0.35, 0.20, 0.50),
                "total": effect_block(0.65, 0.45, 0.85),
            }
        ],
        "sums": [],
    }


def _run_with(result: object, tmp_path: Path) -> dict[str, Any]:
    return run_effects(
        mediation_frame(),
        mediation_config(),
        policy=policy_with(tmp_path, resamples=1000),
        playbook=playbook(),
        rworker=_CannedWorker(result),  # type: ignore[arg-type]
        run_dir=tmp_path,
        call_id="guard-effects",
    )


def _config_variant(hypotheses: list[dict[str, Any]]) -> StudyConfig:
    data = mediation_config().model_dump(mode="python", exclude_none=True, by_alias=True)
    data["hypotheses"] = hypotheses
    return validate_and_build(StudyConfig, data)


# ---- policy settings -------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["many", 0, True],
    ids=["nonnumeric", "zero", "boolean"],
)
def test_doctored_bootstrap_resamples_halts(value: Any) -> None:
    class DoctoredPolicy:
        version = "0.0-test"

        @staticmethod
        def rule(ref: str) -> object:
            values = {
                "effects.bootstrap.resamples": value,
                "effects.bootstrap.ci_level": 0.95,
                "effects.bootstrap.ci_type": "bias_corrected",
            }
            return values[ref]

    with pytest.raises(IntegrityHalt) as excinfo:
        bootstrap_settings(DoctoredPolicy())  # type: ignore[arg-type]
    assert "resamples" in excinfo.value.message


@pytest.mark.parametrize(
    ("ci_level", "ci_type"),
    [(0.0, "bias_corrected"), (1.5, "bias_corrected"), (0.95, "magic")],
    ids=["level_zero", "level_above_one", "unknown_type"],
)
def test_doctored_ci_settings_halt(ci_level: Any, ci_type: str) -> None:
    class DoctoredPolicy:
        version = "0.0-test"

        @staticmethod
        def rule(ref: str) -> object:
            values = {
                "effects.bootstrap.resamples": 500,
                "effects.bootstrap.ci_level": ci_level,
                "effects.bootstrap.ci_type": ci_type,
            }
            return values[ref]

    with pytest.raises(IntegrityHalt) as excinfo:
        bootstrap_settings(DoctoredPolicy())  # type: ignore[arg-type]
    assert "ci_" in excinfo.value.message


# ---- payload builder -------------------------------------------------------


def test_no_indirect_hypothesis_halts(tmp_path: Path) -> None:
    config = _config_variant(
        [{"id": "H1", "effect": "direct", "from": "X", "to": "Y", "sign": "positive"}]
    )
    with pytest.raises(IntegrityHalt) as excinfo:
        build_effects_payload(mediation_frame(), config, policy=policy_with(tmp_path))
    assert "indirect" in excinfo.value.message


def test_indirect_without_via_halts(tmp_path: Path) -> None:
    config = _config_variant(
        [
            {"id": "H1", "effect": "direct", "from": "X", "to": "Y", "sign": "positive"},
            {"id": "H2", "effect": "indirect", "from": "X", "to": "Y", "sign": "positive"},
        ]
    )
    with pytest.raises(IntegrityHalt) as excinfo:
        build_effects_payload(mediation_frame(), config, policy=policy_with(tmp_path))
    assert "via" in excinfo.value.message


def test_via_unknown_construct_halts(tmp_path: Path) -> None:
    config = _config_variant(
        [
            {"id": "H1", "effect": "direct", "from": "X", "to": "Y", "sign": "positive"},
            {
                "id": "H2",
                "effect": "indirect",
                "from": "X",
                "to": "Y",
                "sign": "positive",
                "via": ["MZ"],
            },
        ]
    )
    with pytest.raises(IntegrityHalt) as excinfo:
        build_effects_payload(mediation_frame(), config, policy=policy_with(tmp_path))
    assert "unknown construct" in excinfo.value.message


def test_indirect_without_direct_edge_halts(tmp_path: Path) -> None:
    # PB-17 decomposition (and the Zhao typology) require the direct path
    # to be estimated; an indirect hypothesis without the direct edge in
    # the model halts.
    config = _config_variant(
        [
            {
                "id": "H2",
                "effect": "indirect",
                "from": "X",
                "to": "Y",
                "sign": "positive",
                "via": ["M"],
            }
        ]
    )
    with pytest.raises(IntegrityHalt) as excinfo:
        build_effects_payload(mediation_frame(), config, policy=policy_with(tmp_path))
    assert "direct path" in excinfo.value.message


def test_payload_regressions_cover_chain_and_direct(tmp_path: Path) -> None:
    payload = build_effects_payload(
        mediation_frame(), mediation_config(), policy=policy_with(tmp_path)
    )
    pairs = {(r["lhs"], r["rhs"]) for r in payload["regressions"]}
    assert pairs == {("Y", "X"), ("M", "X"), ("Y", "M")}
    (spec,) = payload["indirect"]
    assert spec == {"id": "H2", "from": "X", "to": "Y", "via": ["M"]}


# ---- worker result validation ----------------------------------------------


def test_nonmapping_result_halts(tmp_path: Path) -> None:
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(["nope"], tmp_path)
    assert "effects" in excinfo.value.message


def test_resamples_echo_mismatch_halts(tmp_path: Path) -> None:
    result = _result(resamples=2500)
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert "resamples" in excinfo.value.message


def test_incomplete_bootstrap_halts(tmp_path: Path) -> None:
    result = _result()
    result["bootstrap"]["completed"] = 999
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert "completed" in excinfo.value.message


def test_missing_hypothesis_id_halts(tmp_path: Path) -> None:
    result = _result()
    result["effects"] = []
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert "missing" in excinfo.value.message


def test_duplicate_hypothesis_id_halts(tmp_path: Path) -> None:
    result = _result()
    result["effects"].append(dict(result["effects"][0]))
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert "duplicate" in excinfo.value.message


def test_extra_hypothesis_id_halts(tmp_path: Path) -> None:
    result = _result()
    result["effects"].append(dict(result["effects"][0], id="H9"))
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert "extra" in excinfo.value.message


@pytest.mark.parametrize("block", ["direct", "indirect", "total"])
@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("est", float("nan")),
        ("se", -0.1),
        ("ci_low", float("inf")),
        ("p", 1.5),
    ],
    ids=["est_nan", "se_negative", "ci_inf", "p_above_one"],
)
def test_invalid_effect_field_halts(
    tmp_path: Path, block: str, field: str, bad_value: float
) -> None:
    result = _result()
    result["effects"][0][block] = dict(result["effects"][0][block], **{field: bad_value})
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert field in excinfo.value.message


def test_ci_out_of_order_halts(tmp_path: Path) -> None:
    result = _result()
    result["effects"][0]["indirect"] = effect_block(0.35, 0.50, 0.20)
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert "ci" in excinfo.value.message


def test_missing_block_halts(tmp_path: Path) -> None:
    result = _result()
    result["effects"][0].pop("total")
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert "total" in excinfo.value.message


def test_missing_bootstrap_block_halts(tmp_path: Path) -> None:
    result = _result()
    result.pop("bootstrap")
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert "bootstrap" in excinfo.value.message


def test_malformed_completed_count_halts(tmp_path: Path) -> None:
    result = _result()
    result["bootstrap"]["completed"] = "many"
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert "completed" in excinfo.value.message


def test_ci_settings_echo_mismatch_halts(tmp_path: Path) -> None:
    result = _result()
    result["bootstrap"]["ci_level"] = 0.90
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert "ci settings" in excinfo.value.message


def test_effects_block_not_list_halts(tmp_path: Path) -> None:
    result = _result()
    result["effects"] = "nope"
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert "effects block" in excinfo.value.message


def test_nonmapping_effects_entry_halts(tmp_path: Path) -> None:
    result = _result()
    result["effects"] = ["nope"]
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert "malformed" in excinfo.value.message


def test_doctored_pb17_without_criteria_halts(tmp_path: Path) -> None:
    class DoctoredPlaybook:
        @staticmethod
        def criteria(step_id: str) -> list[dict[str, Any]]:
            if step_id == "PB-17":
                return [{"name": "resamples"}]
            return []

    with pytest.raises(IntegrityHalt) as excinfo:
        run_effects(
            mediation_frame(),
            mediation_config(),
            policy=policy_with(tmp_path, resamples=1000),
            playbook=DoctoredPlaybook(),  # type: ignore[arg-type]
            rworker=_CannedWorker(_result()),  # type: ignore[arg-type]
            run_dir=tmp_path,
            call_id="guard-pb17",
        )
    assert "PB-17" in excinfo.value.message
