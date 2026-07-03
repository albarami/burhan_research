"""Guard paths for the power/assumptions modules — every halt is typed."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from burhan.core.errors import IntegrityHalt
from burhan.core.playbook import Playbook
from burhan.stats import assumptions as assumptions_module
from burhan.stats import power as power_module
from burhan.stats.assumptions import mahalanobis_feed, mardia, univariate_moments
from burhan.stats.power import minimum_n_close_fit, model_df, n_q_evaluation

REPO = Path(__file__).resolve().parents[3]


class _DoctoredPlaybook:
    """Playbook double returning malformed or absent criteria."""

    def __init__(self, criteria: dict[str, list[dict[str, Any]]]) -> None:
        self._criteria = criteria

    def criteria(self, step_id: str) -> list[dict[str, Any]]:
        return self._criteria.get(step_id, [])


def test_unparseable_univariate_bands_halt() -> None:
    playbook = _DoctoredPlaybook({"PB-05": [{"name": "univariate_bands", "value": "wide"}]})
    with pytest.raises(IntegrityHalt) as excinfo:
        univariate_moments(pd.DataFrame({"x": [1.0, 2.0, 3.0]}), playbook=playbook)  # type: ignore[arg-type]
    assert "univariate_bands" in excinfo.value.message


def test_missing_univariate_bands_criterion_halts() -> None:
    playbook = _DoctoredPlaybook({"PB-05": [{"name": "other"}]})
    with pytest.raises(IntegrityHalt) as excinfo:
        univariate_moments(pd.DataFrame({"x": [1.0, 2.0, 3.0]}), playbook=playbook)  # type: ignore[arg-type]
    assert "lacks" in excinfo.value.message


def test_constant_column_halts_univariate_moments() -> None:
    playbook = Playbook.load(
        REPO / "playbooks" / "CB_SEM_PLAYBOOK_v1.0.yaml", mode="certification"
    )
    with pytest.raises(IntegrityHalt):
        univariate_moments(pd.DataFrame({"flat": [4.0] * 10}), playbook=playbook)


def test_singular_covariance_halts_mardia() -> None:
    rng = np.random.default_rng(2)
    base = rng.normal(0, 1, 30)
    frame = pd.DataFrame({"a": base, "b": 2.0 * base, "c": rng.normal(0, 1, 30)})
    with pytest.raises(IntegrityHalt) as excinfo:
        mardia(frame)
    assert "singular" in excinfo.value.message


def test_mahalanobis_feed_needs_more_cases_than_variables() -> None:
    from burhan.core.policy import Policy

    policy = Policy.load(
        REPO / "policy" / "decision_policy.template.yaml", mode="certification"
    )
    frame = pd.DataFrame(np.eye(3), columns=["a", "b", "c"])
    with pytest.raises(IntegrityHalt):
        mahalanobis_feed(frame, policy=policy)


def test_unreachable_power_target_halts() -> None:
    with pytest.raises(IntegrityHalt) as excinfo:
        minimum_n_close_fit(df=1, target_power=0.9999999, n_ceiling=50)
    assert "unreachable" in excinfo.value.message


def test_saturated_model_halts_model_df() -> None:
    from generator import build_golden

    from burhan.core.artifacts.loader import validate_and_build
    from burhan.core.artifacts.models import StudyConfig

    data = build_golden(11).config
    # inflate hypotheses so q reaches the moment count (78 for 12 items)
    data["model"]["endogenous"] = ["CUL", "INT"]
    for index in range(52):  # 26 + 52 = 78 -> df 0
        data["hypotheses"].append(
            {
                "id": f"H{index + 10}",  # schema id pattern ^H[0-9]+[a-z]?$
                "effect": "direct",
                "from": "RES",
                "to": "CUL",
                "sign": "positive",
            }
        )
    config = validate_and_build(StudyConfig, data)
    with pytest.raises(IntegrityHalt) as excinfo:
        model_df(config)
    assert "degrees of freedom" in excinfo.value.message


def test_unparseable_n_q_target_halts() -> None:
    from generator import build_golden

    from burhan.core.artifacts.loader import validate_and_build
    from burhan.core.artifacts.models import StudyConfig

    config = validate_and_build(StudyConfig, build_golden(11).config)
    playbook = _DoctoredPlaybook({"PB-01": [{"name": "n_to_q_target", "value": "plenty"}]})
    with pytest.raises(IntegrityHalt) as excinfo:
        n_q_evaluation(config, n=300, playbook=playbook)  # type: ignore[arg-type]
    assert "n_to_q_target" in excinfo.value.message


def test_missing_n_q_criterion_halts() -> None:
    from generator import build_golden

    from burhan.core.artifacts.loader import validate_and_build
    from burhan.core.artifacts.models import StudyConfig

    config = validate_and_build(StudyConfig, build_golden(11).config)
    playbook = _DoctoredPlaybook({"PB-01": []})
    with pytest.raises(IntegrityHalt) as excinfo:
        n_q_evaluation(config, n=300, playbook=playbook)  # type: ignore[arg-type]
    assert "lacks" in excinfo.value.message


def test_modules_expose_no_montecarlo_placeholder() -> None:
    # FR-401's Monte Carlo is escalated (E-R3); until the governed R stack
    # lands, no function pretends to provide it (no placeholder statistics).
    public_power = [n for n in dir(power_module) if not n.startswith("_")]
    public_assumptions = [n for n in dir(assumptions_module) if not n.startswith("_")]
    for name in public_power + public_assumptions:
        assert "montecarlo" not in name.lower()
        assert "simsem" not in name.lower()
