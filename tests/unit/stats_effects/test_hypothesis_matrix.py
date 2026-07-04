"""AT-M11-4: the hypothesis matrix (PB-16; FR-1103 backbone).

Verdicts follow the PB-16 significance rule including marginal-p = not
supported and sign consistency; every row carries statistic IDs and no
raw numbers, so TC-13's checker inherits a clean substrate.
"""

from __future__ import annotations

from typing import Any

import pytest
from effects_util import effect_block, mediation_config, playbook

from burhan.core.errors import IntegrityHalt
from burhan.stats.effects import effects_store_rows
from burhan.stats.hypothesis_matrix import build_hypothesis_matrix


def _report(
    *,
    direct: dict[str, Any] | None = None,
    indirect: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "bootstrap": {
            "resamples": 300,
            "completed": 300,
            "ci_level": 0.95,
            "ci_type": "bias_corrected",
        },
        "paths": [],
        "effects": [
            {
                "hypothesis": "H2",
                "from": "X",
                "to": "Y",
                "via": ["M"],
                "direct": direct if direct is not None else effect_block(0.30, 0.15, 0.45),
                "indirect": indirect if indirect is not None else effect_block(0.35, 0.20, 0.50),
                "total": effect_block(0.65, 0.45, 0.85),
                "classification": "complementary",
            }
        ],
        "sums": [],
    }


def _matrix(report: dict[str, Any]) -> list[dict[str, Any]]:
    return build_hypothesis_matrix(mediation_config(), report, playbook=playbook())


def test_supported_hypotheses() -> None:
    rows = _matrix(_report(direct=dict(effect_block(0.30, 0.15, 0.45), p=0.001)))
    by_id = {row["hypothesis"]: row for row in rows}
    assert by_id["H1"]["verdict"] == "supported"
    assert by_id["H2"]["verdict"] == "supported"
    assert by_id["H1"]["path"] == "X -> Y"
    assert by_id["H2"]["path"] == "X -> M -> Y"


def test_marginal_p_is_not_supported() -> None:
    # PB-16: marginal (.05–.10) reported as not supported, even with a
    # CI excluding zero.
    rows = _matrix(_report(direct=dict(effect_block(0.30, 0.15, 0.45), p=0.07)))
    by_id = {row["hypothesis"]: row for row in rows}
    assert by_id["H1"]["verdict"] == "not_supported"


def test_p_just_below_alpha_is_supported() -> None:
    rows = _matrix(_report(direct=dict(effect_block(0.30, 0.15, 0.45), p=0.04)))
    by_id = {row["hypothesis"]: row for row in rows}
    assert by_id["H1"]["verdict"] == "supported"


def test_insignificant_effect_not_supported() -> None:
    rows = _matrix(_report(indirect=effect_block(0.05, -0.05, 0.15)))
    by_id = {row["hypothesis"]: row for row in rows}
    assert by_id["H2"]["verdict"] == "not_supported"


def test_sign_mismatch_not_supported() -> None:
    # A significant NEGATIVE estimate cannot support a positive
    # hypothesis.
    rows = _matrix(_report(direct=dict(effect_block(-0.30, -0.45, -0.15), p=0.001)))
    by_id = {row["hypothesis"]: row for row in rows}
    assert by_id["H1"]["verdict"] == "not_supported"


def test_rows_carry_only_statistic_ids_never_numbers() -> None:
    rows = _matrix(_report())
    assert {row["hypothesis"] for row in rows} == {"H1", "H2"}
    for row in rows:
        for key, value in row.items():
            assert isinstance(value, str), (row["hypothesis"], key)
    by_id = {row["hypothesis"]: row for row in rows}
    assert by_id["H1"]["statistic_id"] == "effects.direct.X->Y"
    assert by_id["H2"]["statistic_id"] == "effects.indirect.X->Y.via_M"
    assert by_id["H2"]["classification_id"] == "effects.classification.X->Y.via_M"
    assert by_id["H1"]["rule_id"] == "PB-16.significance_rule"


def test_matrix_ids_resolve_against_store_rows() -> None:
    report = _report()
    rows = _matrix(report)
    store_ids = {
        entry["id"] for entry in effects_store_rows(report, created="2026-07-04T00:00:00Z")
    }
    for row in rows:
        assert row["statistic_id"] in store_ids, row["hypothesis"]
        if "classification_id" in row:
            assert row["classification_id"] in store_ids


def test_store_rows_are_schema_shaped() -> None:
    entries = effects_store_rows(_report(), created="2026-07-04T00:00:00Z")
    by_id = {entry["id"]: entry for entry in entries}
    direct = by_id["effects.direct.X->Y"]
    assert direct["stage"] == "effects"
    assert direct["engine"] == "r_lavaan"
    assert direct["playbook_step"] == "PB-17"
    assert direct["ci_low"] == 0.15
    assert direct["ci_high"] == 0.45
    assert direct["ci_level"] == 0.95
    classification = by_id["effects.classification.X->Y.via_M"]
    assert classification["value"] == "complementary"
    with_p = effects_store_rows(
        _report(direct=dict(effect_block(0.30, 0.15, 0.45), p=0.001)),
        created="2026-07-04T00:00:00Z",
    )
    direct_with_p = {entry["id"]: entry for entry in with_p}["effects.direct.X->Y"]
    assert direct_with_p["p"] == 0.001


def test_hypothesis_without_computed_statistic_halts() -> None:
    report = _report()
    report["effects"] = []
    with pytest.raises(IntegrityHalt) as excinfo:
        _matrix(report)
    assert "no computed statistic" in excinfo.value.message


def test_indirect_with_unmatched_via_halts() -> None:
    report = _report()
    report["effects"][0]["via"] = ["Z"]
    with pytest.raises(IntegrityHalt) as excinfo:
        _matrix(report)
    assert "no computed statistic" in excinfo.value.message


def test_total_hypothesis_row() -> None:
    from effects_util import mediation_config as base_config

    from burhan.core.artifacts.loader import validate_and_build
    from burhan.core.artifacts.models import StudyConfig

    data = base_config().model_dump(mode="python", exclude_none=True, by_alias=True)
    data["hypotheses"].append(
        {"id": "H3", "effect": "total", "from": "X", "to": "Y", "sign": "positive"}
    )
    config = validate_and_build(StudyConfig, data)
    rows = build_hypothesis_matrix(config, _report(), playbook=playbook())
    by_id = {row["hypothesis"]: row for row in rows}
    assert by_id["H3"]["statistic_id"] == "effects.total.X->Y"
    assert by_id["H3"]["verdict"] == "supported"


def test_total_hypothesis_without_statistic_halts() -> None:
    from burhan.core.artifacts.loader import validate_and_build
    from burhan.core.artifacts.models import StudyConfig

    data = mediation_config().model_dump(mode="python", exclude_none=True, by_alias=True)
    data["hypotheses"].append(
        {"id": "H3", "effect": "total", "from": "M", "to": "Y", "sign": "positive"}
    )
    config = validate_and_build(StudyConfig, data)
    with pytest.raises(IntegrityHalt) as excinfo:
        build_hypothesis_matrix(config, _report(), playbook=playbook())
    assert "no computed statistic" in excinfo.value.message


def test_preceding_unrelated_criterion_is_skipped() -> None:
    real = playbook()

    class DoctoredPlaybook:
        @staticmethod
        def criteria(step_id: str) -> list[dict[str, Any]]:
            crits = real.criteria(step_id)
            if step_id == "PB-16":
                return [{"name": "other", "value": 1.0}, *crits]
            return crits

    rows = build_hypothesis_matrix(
        mediation_config(),
        _report(),
        playbook=DoctoredPlaybook(),  # type: ignore[arg-type]
    )
    assert {row["hypothesis"] for row in rows} == {"H1", "H2"}


@pytest.mark.parametrize(
    "doctor",
    [
        lambda crits: [],
        lambda crits: [dict(c, rule="be significant") for c in crits],
        lambda crits: [dict(c, value="small") for c in crits],
    ],
    ids=["missing_rule", "unparseable_marginal", "nonnumeric_alpha"],
)
def test_doctored_playbook_halts(doctor: Any) -> None:
    real = playbook()

    class DoctoredPlaybook:
        @staticmethod
        def criteria(step_id: str) -> list[dict[str, Any]]:
            crits = real.criteria(step_id)
            if step_id == "PB-16":
                return doctor([dict(c) for c in crits])
            return crits

    with pytest.raises(IntegrityHalt):
        build_hypothesis_matrix(
            mediation_config(),
            _report(),
            playbook=DoctoredPlaybook(),  # type: ignore[arg-type]
        )
