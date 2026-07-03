"""Estimator determination (AT-M09-4; FR-602/603; PB-07).

Three fixtures: clean 7-category → ML; multivariate-kurtotic (a case-level
scale mixture whose univariate moments stay far inside the 2/7 bands while
Mardia rejects at p≈0) → MLR; 4-category → WLSMV. Each determination emits
a DecisionEntry through TC-02's policy engine with rationale and PB-07
citations — never ad-hoc logging.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from burhan.core.playbook import Playbook
from burhan.core.policy import DecisionLog, Policy, replay_decision_entries
from burhan.stats.assumptions import estimator_determination

REPO = Path(__file__).resolve().parents[3]


class FixedClock:
    def now(self) -> dt.datetime:
        return dt.datetime(2026, 7, 3, 9, 0, 0, tzinfo=dt.UTC)


def _playbook() -> Playbook:
    return Playbook.load(REPO / "playbooks" / "CB_SEM_PLAYBOOK_v1.0.yaml", mode="certification")


def _policy() -> Policy:
    return Policy.load(REPO / "policy" / "decision_policy.template.yaml", mode="certification")


def _fixture(kind: str, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n, p = 250, 6
    latent = rng.normal(0, 1, (n, 1))
    z = 0.7 * latent + 0.7 * rng.normal(0, 1, (n, p))
    if kind == "violate":
        weights = np.where(rng.random(n) < 0.18, 2.4, 0.85)[:, None]
        z = z * weights
    if kind == "four":
        values = np.clip(np.round(2.5 + z), 1, 4)
    else:
        values = np.clip(np.round(4 + 1.2 * z), 1, 7)
    return pd.DataFrame(values, columns=[f"X{i}" for i in range(1, p + 1)])


def _determine(kind: str, tmp_path: Path) -> tuple[dict[str, Any], Path]:
    log_path = tmp_path / "decisions.jsonl"
    log = DecisionLog(log_path, FixedClock())
    determination = estimator_determination(
        _fixture(kind),
        policy=_policy(),
        playbook=_playbook(),
        decision_log=log,
    )
    return determination, log_path


def test_clean_seven_category_determines_ml(tmp_path: Path) -> None:  # AT-M09-4
    determination, log_path = _determine("clean", tmp_path)
    assert determination["estimator"] == "ml"
    entries = replay_decision_entries(log_path)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.stage == "assumptions"
    assert entry.decision_point == "estimator_determination"
    assert entry.rule_id == "estimator.default"
    assert entry.decision == "ml"
    assert "categories" in entry.inputs
    assert entry.rationale  # non-empty, human-readable
    assert any("Rhemtulla" in a or "rhemtulla2012" in a for a in determination["citations"])


def test_mardia_violation_determines_mlr(tmp_path: Path) -> None:  # AT-M09-4
    determination, log_path = _determine("violate", tmp_path)
    assert determination["estimator"] == "mlr"
    entry = replay_decision_entries(log_path)[0]
    assert entry.rule_id == "estimator.robust_trigger.on_mardia_violation"
    assert entry.decision == "mlr"
    assert entry.inputs["mardia_violation"] is True
    assert any("Satorra" in c or "satorra" in c for c in determination["citations"])


def test_four_category_determines_wlsmv(tmp_path: Path) -> None:  # AT-M09-4
    determination, log_path = _determine("four", tmp_path)
    assert determination["estimator"] == "wlsmv"
    entry = replay_decision_entries(log_path)[0]
    assert entry.rule_id == "estimator.wlsmv_conditions"
    assert entry.decision == "wlsmv"
    assert entry.inputs["categories"] == 4
    assert determination["basis"] == "polychoric"


def test_determination_inputs_carry_policy_values(tmp_path: Path) -> None:
    # The decision evidence records the governed thresholds it evaluated —
    # proof the determination read policy paths, not literals.
    _, log_path = _determine("four", tmp_path)
    entry = replay_decision_entries(log_path)[0]
    assert entry.inputs["max_categories_for_categorical"] == 4
    assert entry.rule_version == _policy().version


def test_citations_resolve_through_the_playbook(tmp_path: Path) -> None:
    determination, _ = _determine("clean", tmp_path)
    for citation in determination["citations"]:
        assert len(citation) > 20  # full reference strings, not bare keys
