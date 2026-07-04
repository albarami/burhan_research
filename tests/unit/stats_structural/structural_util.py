"""Deterministic fixtures for the structural stage (AT-M11-1/5).

The benchmark frame is the committed Mplus UG ex5.11 dataset (see
PROVENANCE.md). The carry frame is a pure function of its seed: two
first-order constructs driven by one general factor (the second-order
signal) plus an outcome construct the general factor predicts — enough
latent structure for both carriers to fit distinguishable real models.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig
from burhan.core.playbook import Playbook

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def playbook() -> Playbook:
    return Playbook.load(REPO / "playbooks" / "CB_SEM_PLAYBOOK_v1.0.yaml", mode="certification")


def benchmark_frame() -> pd.DataFrame:
    frame = pd.read_csv(
        HERE / "ex5.11.dat", sep=r"\s+", header=None, names=[f"y{i}" for i in range(1, 13)]
    )
    frame.index = pd.Index([f"R_{i:04d}" for i in range(1, len(frame) + 1)], name="case")
    return frame


def _base_config(
    items: dict[str, list[str]],
    constructs: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]],
    model: dict[str, Any],
    higher_order: dict[str, Any] | None,
) -> StudyConfig:
    data: dict[str, Any] = {
        "schema_version": 1,
        "meta": {
            "study_id": "structural-fixture-2026",
            "title": "Structural stage fixture",
            "source_documents": [
                {"role": "study_document", "path": "inputs/s.docx", "sha256": "b" * 64}
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
                }
                for construct, codes in items.items()
                for code in codes
            ]
        },
        "constructs": constructs,
        "model": model,
        "hypotheses": hypotheses,
        "data": {"file": "inputs/s.csv", "format": "csv"},
    }
    if higher_order is not None:
        data["higher_order"] = higher_order
    return validate_and_build(StudyConfig, data)


def benchmark_config() -> StudyConfig:
    """The ex5.11 model as a study contract (four factors, two regressions)."""
    items = {f"F{k}": [f"y{(k - 1) * 3 + j}" for j in (1, 2, 3)] for k in (1, 2, 3, 4)}
    constructs: list[dict[str, Any]] = [
        {
            "code": code,
            "name": f"Factor {code}",
            "level": "first_order",
            "measurement": "reflective",
            "indicators": list(codes),
        }
        for code, codes in items.items()
    ]
    hypotheses = [
        {"id": "H1", "effect": "direct", "from": "F1", "to": "F3", "sign": "positive"},
        {"id": "H2", "effect": "direct", "from": "F2", "to": "F3", "sign": "positive"},
        {"id": "H3", "effect": "direct", "from": "F3", "to": "F4", "sign": "positive"},
    ]
    model = {"exogenous": ["F1", "F2"], "endogenous": ["F3", "F4"]}
    return _base_config(items, constructs, hypotheses, model, None)


_CARRY_ITEMS = {
    "FA": ["A1", "A2", "A3"],
    "FB": ["B1", "B2", "B3"],
    "OUT": ["C1", "C2", "C3"],
}


def carry_config(carry: str) -> StudyConfig:
    """Second-order F5 (FA+FB) predicting OUT, carrier per contract."""
    constructs: list[dict[str, Any]] = [
        {
            "code": code,
            "name": f"Construct {code}",
            "level": "first_order",
            "measurement": "reflective",
            "indicators": list(codes),
        }
        for code, codes in _CARRY_ITEMS.items()
    ]
    constructs.append(
        {
            "code": "F5",
            "name": "General factor",
            "level": "second_order",
            "measurement": "reflective",
            "components": ["FA", "FB"],
        }
    )
    hypotheses = [{"id": "H1", "effect": "direct", "from": "F5", "to": "OUT", "sign": "positive"}]
    model = {"exogenous": ["F5"], "endogenous": ["OUT"]}
    higher_order = {
        "approach": "repeated_indicator",
        "structural_carry": carry,
        "citation": "Sarstedt et al. (2019)",
    }
    return _base_config(_CARRY_ITEMS, constructs, hypotheses, model, higher_order)


def carry_frame(seed: int = 53, *, n: int = 300) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    general = rng.normal(0.0, 1.0, n)
    factor_a = 0.80 * general + 0.60 * rng.normal(0.0, 1.0, n)
    factor_b = 0.75 * general + 0.66 * rng.normal(0.0, 1.0, n)
    outcome = 0.60 * general + 0.80 * rng.normal(0.0, 1.0, n)
    latents = {"A": factor_a, "B": factor_b, "C": outcome}
    columns: dict[str, Any] = {}
    for prefix, latent in latents.items():
        for j in (1, 2, 3):
            columns[f"{prefix}{j}"] = 0.75 * latent + 0.66 * rng.normal(0.0, 1.0, n)
    frame = pd.DataFrame(columns)
    frame.index = pd.Index([f"R_{i:04d}" for i in range(1, n + 1)], name="case")
    return frame
