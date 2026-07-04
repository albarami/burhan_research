"""Deterministic fixtures for the verification lane (AT-M12-1/2/3/5)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from burhan.core.playbook import Playbook
from burhan.core.policy import Policy

REPO = Path(__file__).resolve().parents[3]


class FixedClock:
    def now(self) -> dt.datetime:
        return dt.datetime(2026, 7, 4, 12, 0, 0, tzinfo=dt.UTC)


def policy() -> Policy:
    return Policy.load(REPO / "policy" / "decision_policy.template.yaml", mode="certification")


def playbook() -> Playbook:
    return Playbook.load(REPO / "playbooks" / "CB_SEM_PLAYBOOK_v1.0.yaml", mode="certification")


def parity_map_data() -> dict[str, Any]:
    """A minimal certified-map shape mirroring the benchmark runner's output."""
    return {
        "schema_version": 1,
        "certified": {
            "structural.paths": {"tolerance": 0.001},
            "measurement.loadings": {"tolerance": 0.001},
        },
        "non_parity": ["estimator.wlsmv"],
    }


def pair(
    scope: str,
    stat_id: str,
    engine: float,
    independent: float,
) -> dict[str, Any]:
    return {
        "scope": scope,
        "id": stat_id,
        "engine_value": engine,
        "independent_value": independent,
    }
