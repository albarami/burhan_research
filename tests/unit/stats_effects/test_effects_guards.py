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
        "paths": [
            {
                "lhs": lhs,
                "rhs": rhs,
                "est": 0.4,
                "se": 0.05,
                "ci_low": 0.3,
                "ci_high": 0.5,
                "p": 0.01,
            }
            for lhs, rhs in (("Y", "X"), ("M", "X"), ("Y", "M"))
        ],
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


def test_indirect_without_direct_edge_builds_chain_only_model(tmp_path: Path) -> None:
    # A contract may hypothesize mediation without a direct edge — the
    # direct effect is then constrained to zero by the declared model
    # (the published ex3.16 anchor has exactly this shape).
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
    payload = build_effects_payload(mediation_frame(), config, policy=policy_with(tmp_path))
    pairs = {(r["lhs"], r["rhs"]) for r in payload["regressions"]}
    assert pairs == {("M", "X"), ("Y", "M")}


def test_no_direct_edge_report_carries_none_blocks(tmp_path: Path) -> None:
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
    result = _result()
    result["effects"][0]["direct"] = None
    result["effects"][0]["total"] = None
    result["paths"] = [row for row in result["paths"] if (row["lhs"], row["rhs"]) != ("Y", "X")]
    report = run_effects(
        mediation_frame(),
        config,
        policy=policy_with(tmp_path, resamples=1000),
        playbook=playbook(),
        rworker=_CannedWorker(result),  # type: ignore[arg-type]
        run_dir=tmp_path,
        call_id="guard-nodirect",
    )
    (entry,) = report["effects"]
    assert entry["direct"] is None
    assert entry["total"] is None
    assert entry["classification"] == "indirect_only"


def test_direct_block_for_undeclared_edge_halts(tmp_path: Path) -> None:
    # The worker must not invent a direct effect the model never declared.
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
        run_effects(
            mediation_frame(),
            config,
            policy=policy_with(tmp_path, resamples=1000),
            playbook=playbook(),
            rworker=_CannedWorker(_result()),  # type: ignore[arg-type]
            run_dir=tmp_path,
            call_id="guard-invented-direct",
        )
    assert "undeclared direct edge" in excinfo.value.message


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


def _path_row(lhs: str, rhs: str, **overrides: Any) -> dict[str, Any]:
    row = {"lhs": lhs, "rhs": rhs, "est": 0.4, "se": 0.05, "ci_low": 0.3, "ci_high": 0.5, "p": 0.01}
    row.update(overrides)
    return row


def _full_paths() -> list[dict[str, Any]]:
    return [_path_row("Y", "X"), _path_row("M", "X"), _path_row("Y", "M")]


def test_paths_must_cover_model_pairs_exactly(tmp_path: Path) -> None:
    result = _result()
    result["paths"] = _full_paths()[:2]
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert "missing" in excinfo.value.message
    result = _result()
    result["paths"] = [*_full_paths(), _path_row("NOPE", "FZ")]
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert "extra" in excinfo.value.message
    result = _result()
    result["paths"] = [*_full_paths(), _path_row("Y", "X")]
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert "duplicate" in excinfo.value.message


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("est", "not-a-number"),
        ("est", float("nan")),
        ("se", -0.1),
        ("ci_low", float("inf")),
        ("p", 1.5),
    ],
    ids=["est_str", "est_nan", "se_negative", "ci_inf", "p_above_one"],
)
def test_malformed_path_entry_halts(tmp_path: Path, field: str, bad_value: Any) -> None:
    result = _result()
    result["paths"] = _full_paths()
    result["paths"][0][field] = bad_value
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert field in excinfo.value.message


def test_unexpected_sum_group_halts(tmp_path: Path) -> None:
    # One indirect spec per pair -> no sums expected; a worker sum is an
    # extra unrequested group, never silently accepted.
    result = _result()
    result["sums"] = [
        {"from": "X", "to": "Y", "est": 0.35, "se": 0.05, "ci_low": 0.2, "ci_high": 0.5, "p": None}
    ]
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert "extra" in excinfo.value.message


def test_malformed_sum_entry_halts(tmp_path: Path) -> None:
    result = _result()
    result["sums"] = [
        {"from": "X", "to": "Y", "est": float("nan"), "se": 0.05, "ci_low": 0.1, "ci_high": 0.2}
    ]
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert "est" in excinfo.value.message or "extra" in excinfo.value.message


@pytest.mark.parametrize(
    ("mutate", "named"),
    [
        (lambda r: r.update(paths="nope"), "paths block"),
        (lambda r: r.update(paths=[{"lhs": "Y"}]), "paths entry"),
        (lambda r: r.update(sums="nope"), "sums block"),
        (lambda r: r.update(sums=["nope"]), "sums entry"),
    ],
    ids=["paths_not_list", "paths_entry_malformed", "sums_not_list", "sums_entry_malformed"],
)
def test_malformed_paths_sums_shapes_halt(tmp_path: Path, mutate: Any, named: str) -> None:
    result = _result()
    mutate(result)
    with pytest.raises(IntegrityHalt) as excinfo:
        _run_with(result, tmp_path)
    assert named in excinfo.value.message


def _two_indirect_config() -> StudyConfig:
    return _config_variant(
        [
            {"id": "H1", "effect": "direct", "from": "X", "to": "Y", "sign": "positive"},
            {
                "id": "H2",
                "effect": "indirect",
                "from": "X",
                "to": "Y",
                "sign": "positive",
                "via": ["M"],
            },
            {
                "id": "H3",
                "effect": "indirect",
                "from": "X",
                "to": "Y",
                "sign": "positive",
                "via": ["M"],
            },
        ]
    )


def _two_indirect_result(sums: list[dict[str, Any]]) -> dict[str, Any]:
    result = _result()
    result["effects"] = [
        dict(result["effects"][0], id="H2"),
        dict(result["effects"][0], id="H3"),
    ]
    result["sums"] = sums
    return result


def test_missing_expected_sum_group_halts(tmp_path: Path) -> None:
    # Two indirect specs on the same pair -> the per-pair sum is a
    # contract output; a worker omitting it halts.
    with pytest.raises(IntegrityHalt) as excinfo:
        run_effects(
            mediation_frame(),
            _two_indirect_config(),
            policy=policy_with(tmp_path, resamples=1000),
            playbook=playbook(),
            rworker=_CannedWorker(_two_indirect_result([])),  # type: ignore[arg-type]
            run_dir=tmp_path,
            call_id="guard-missing-sum",
        )
    assert "missing" in excinfo.value.message


def test_duplicate_sum_group_halts(tmp_path: Path) -> None:
    sum_block = {
        "from": "X",
        "to": "Y",
        "est": 0.7,
        "se": 0.05,
        "ci_low": 0.5,
        "ci_high": 0.9,
        "p": None,
    }
    with pytest.raises(IntegrityHalt) as excinfo:
        run_effects(
            mediation_frame(),
            _two_indirect_config(),
            policy=policy_with(tmp_path, resamples=1000),
            playbook=playbook(),
            rworker=_CannedWorker(  # type: ignore[arg-type]
                _two_indirect_result([sum_block, dict(sum_block)])
            ),
            run_dir=tmp_path,
            call_id="guard-dup-sum",
        )
    assert "duplicate" in excinfo.value.message


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
