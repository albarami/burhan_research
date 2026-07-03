"""Deterministic fixtures for the deletion protocol and respecification.

Workers here are canned/spy doubles: AT-M10-4 is about the *controller's*
governance behavior (protected default, one-at-a-time re-estimation,
dual trigger, floors), which the call sequence proves; no live R fit is
required. Frames are pure functions of their seed (no ambient RNG) and
exist only to satisfy the payload builder's completeness checks.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig
from burhan.core.playbook import Playbook
from burhan.core.policy import DecisionLog, Policy
from burhan.core.registry import Registry

REPO = Path(__file__).resolve().parents[3]


class FixedClock:
    """Deterministic clock for DecisionLog entries."""

    def __init__(self) -> None:
        self._tick = 0

    def now(self) -> dt.datetime:
        self._tick += 1
        return dt.datetime(2026, 7, 3, 12, 0, self._tick % 60, tzinfo=dt.UTC)


class SequenceWorker:
    """Spy worker: returns canned results in order, records every payload."""

    def __init__(self, results: list[dict[str, Any]]) -> None:
        self._results = list(results)
        self.calls: list[dict[str, Any]] = []

    def call(self, *args: object, **kwargs: object) -> dict[str, Any]:
        payload = args[1] if len(args) > 1 else kwargs.get("payload")
        assert isinstance(payload, dict)
        self.calls.append(payload)
        if not self._results:
            raise AssertionError("SequenceWorker exhausted: unexpected extra call")
        return self._results.pop(0)


def playbook() -> Playbook:
    return Playbook.load(REPO / "playbooks" / "CB_SEM_PLAYBOOK_v1.0.yaml", mode="certification")


def policy_with(
    preauthorized: bool,
    tmp_path: Path,
    *,
    cap: int | None = None,
    rules: list[str] | None = None,
) -> Policy:
    """Load the template policy, toggling the PD-05 switch (and cap) only."""
    import yaml

    source = (REPO / "policy" / "decision_policy.template.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(source)
    data["measurement"]["item_deletion"]["preauthorized"] = preauthorized
    if preauthorized:
        data["measurement"]["item_deletion"]["preauthorized_rules"] = (
            rules if rules is not None else ["loading_below_playbook_target"]
        )
    if cap is not None:
        data["measurement"]["respecification"]["max_modifications"] = cap
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return Policy.load(path, mode="certification")


def decision_log(tmp_path: Path) -> DecisionLog:
    return DecisionLog(tmp_path / "decisions.jsonl", FixedClock())


def registry(policy: Policy) -> Registry:
    return Registry.load(
        REPO / "policy" / "protected_decisions.registry.yaml",
        mode="certification",
        policy=policy,
    )


def frame_for(items: list[str], *, seed: int = 41, n: int = 80) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame({code: rng.normal(0.0, 1.0, n) for code in items})
    frame.index = pd.Index([f"R_{i:04d}" for i in range(1, n + 1)], name="case")
    return frame


def study_config(
    constructs: dict[str, list[str]],
    *,
    sources: dict[str, str] | None = None,
    item_sources: dict[str, str] | None = None,
) -> StudyConfig:
    """A schema-valid contract; ``sources`` marks validated instruments."""
    sources = sources or {}
    item_sources = item_sources or {}
    codes = [code for items in constructs.values() for code in items]
    data: dict[str, Any] = {
        "schema_version": 1,
        "meta": {
            "study_id": "deletion-fixture-2026",
            "title": "Deletion protocol fixture",
            "source_documents": [
                {"role": "study_document", "path": "inputs/d.docx", "sha256": "a" * 64}
            ],
        },
        "methodology": {
            "declared": "CB_SEM",
            "playbook_id": "CB_SEM_PLAYBOOK",
            "playbook_version": "1.0",
            "design": "cross_sectional",
        },
        "instrument": {
            "items": [
                {
                    "code": code,
                    "text": f"{code} statement.",
                    "construct_ref": construct,
                    "scale": {"type": "numeric", "min": -10, "max": 10},
                    "reverse_coded": False,
                    "column_hint": f"Q_{code}",
                    **({"source": item_sources[code]} if code in item_sources else {}),
                }
                for construct, items in constructs.items()
                for code in items
            ]
        },
        "constructs": [
            {
                "code": construct,
                "name": f"Construct {construct}",
                "level": "first_order",
                "measurement": "reflective",
                "indicators": list(items),
                **({"source": sources[construct]} if construct in sources else {}),
            }
            for construct, items in constructs.items()
        ],
        "model": {"exogenous": [next(iter(constructs))], "endogenous": [list(constructs)[-1]]},
        "hypotheses": [
            {
                "id": "H1",
                "effect": "direct",
                "from": next(iter(constructs)),
                "to": list(constructs)[-1],
                "sign": "positive",
            }
        ],
        "data": {"file": "inputs/d.csv", "format": "csv"},
    }
    assert len(codes) == len(set(codes))
    return validate_and_build(StudyConfig, data)


def worker_result(
    constructs: dict[str, list[str]],
    std_by_item: dict[str, float] | None = None,
    *,
    fit_chisq: float = 120.0,
) -> dict[str, Any]:
    """A complete, valid measurement worker result for canned sequences."""
    std_by_item = std_by_item or {}
    loadings = [
        {
            "construct": construct,
            "item": code,
            "est": std_by_item.get(code, 0.75),
            "std": std_by_item.get(code, 0.75),
            "se": 0.05,
            "p": 0.001,
        }
        for construct, items in constructs.items()
        for code in items
    ]
    reliability = [
        {"construct": construct, "alpha": 0.85, "cr": 0.86, "ave": 0.57} for construct in constructs
    ]
    return {
        "approach": "first_order_only",
        "first_order": {"loadings": loadings, "reliability": reliability},
        "second_order": None,
        "fit": {"chisq": fit_chisq, "df": 24},
        "validity": {"latent_correlations": [], "htmt": []},
    }
