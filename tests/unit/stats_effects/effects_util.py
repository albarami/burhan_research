"""Deterministic fixtures for the effects stage (AT-M11-2/3/4).

The benchmark frame is the committed Mplus UG ex3.11 dataset (see
PROVENANCE.md). The mediation frame is a pure function of its seed and
population parameters: an X → M → Y latent chain (three indicators
each) with a tunable direct edge, so each Zhao–Lynch–Chen fixture is
generated from its own (a, b, c) triple.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig
from burhan.core.playbook import Playbook
from burhan.core.policy import Policy

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def playbook() -> Playbook:
    return Playbook.load(REPO / "playbooks" / "CB_SEM_PLAYBOOK_v1.0.yaml", mode="certification")


def policy_with(tmp_path: Path, *, resamples: int | None = None) -> Policy:
    """The template policy, optionally overriding the bootstrap resamples."""
    import yaml

    source = (REPO / "policy" / "decision_policy.template.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(source)
    if resamples is not None:
        data["effects"]["bootstrap"]["resamples"] = resamples
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return Policy.load(path, mode="certification")


def benchmark_frame() -> pd.DataFrame:
    frame = pd.read_csv(
        HERE / "ex3.11.dat",
        sep=r"\s+",
        header=None,
        names=["y1", "y2", "y3", "x1", "x2", "x3"],
    )
    frame.index = pd.Index([f"R_{i:04d}" for i in range(1, len(frame) + 1)], name="case")
    return frame


_MED_ITEMS = {"X": ["X1", "X2", "X3"], "M": ["M1", "M2", "M3"], "Y": ["Y1", "Y2", "Y3"]}


def mediation_config() -> StudyConfig:
    """X → M → Y with a hypothesized direct and indirect effect."""
    data: dict[str, Any] = {
        "schema_version": 1,
        "meta": {
            "study_id": "effects-fixture-2026",
            "title": "Effects stage fixture",
            "source_documents": [
                {"role": "study_document", "path": "inputs/e.docx", "sha256": "c" * 64}
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
                for construct, codes in _MED_ITEMS.items()
                for code in codes
            ]
        },
        "constructs": [
            {
                "code": construct,
                "name": f"Construct {construct}",
                "level": "first_order",
                "measurement": "reflective",
                "indicators": list(codes),
            }
            for construct, codes in _MED_ITEMS.items()
        ],
        "model": {"exogenous": ["X"], "endogenous": ["Y"], "mediators": ["M"]},
        "hypotheses": [
            {"id": "H1", "effect": "direct", "from": "X", "to": "Y", "sign": "positive"},
            {
                "id": "H2",
                "effect": "indirect",
                "from": "X",
                "to": "Y",
                "sign": "positive",
                "via": ["M"],
            },
        ],
        "data": {"file": "inputs/e.csv", "format": "csv"},
    }
    return validate_and_build(StudyConfig, data)


def mediation_frame(
    seed: int = 61, *, a: float = 0.6, b: float = 0.6, c: float = 0.5, n: int = 350
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x = rng.normal(0.0, 1.0, n)
    m = a * x + float(np.sqrt(max(1.0 - a**2, 0.2))) * rng.normal(0.0, 1.0, n)
    y = b * m + c * x + 0.8 * rng.normal(0.0, 1.0, n)
    latents = {"X": x, "M": m, "Y": y}
    columns: dict[str, Any] = {}
    for construct, codes in _MED_ITEMS.items():
        latent = latents[construct]
        for code in codes:
            columns[code] = 0.75 * latent + 0.66 * rng.normal(0.0, 1.0, n)
    frame = pd.DataFrame(columns)
    frame.index = pd.Index([f"R_{i:04d}" for i in range(1, n + 1)], name="case")
    return frame


def effect_block(est: float, ci_low: float, ci_high: float, *, se: float = 0.05) -> dict[str, Any]:
    """A valid worker effect block for canned classification fixtures."""
    return {"est": est, "se": se, "ci_low": ci_low, "ci_high": ci_high, "p": None}
