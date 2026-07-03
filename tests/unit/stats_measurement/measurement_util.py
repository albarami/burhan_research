"""Deterministic fixtures for the measurement battery (AT-M10-2/3).

Every dataset is a pure function of its seed (numpy default_rng; no
ambient RNG). Reference values for the validity battery are captured
from the renv-locked semTools on these exact fixtures and pinned in the
tests with provenance.

- ``validity_frame``: two clean constructs (4 items each, standardized
  loadings ≈ .75, latent correlation .55) — the pass-everything battery.
- ``trap_frame``: the PB-11 near-redundant pair — latent correlation .87
  with loadings ≈ .92, so AVE ≈ .84 exceeds r² ≈ .76 (Fornell–Larcker
  passes) while HTMT ≈ .87 lands in the governed flag band.
- ``cmb_frame``: two constructs with an injected common method factor
  (method loadings ≈ .75 dominate construct loadings ≈ .45); the clean
  twin has no method factor.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

_ITEMS_A = ("A1", "A2", "A3", "A4")
_ITEMS_B = ("B1", "B2", "B3", "B4")


def _two_construct_frame(
    seed: int,
    *,
    n: int,
    latent_corr: float,
    loading: float,
    method_loading: float = 0.0,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    noise_sd = float(np.sqrt(max(1.0 - loading**2 - method_loading**2, 0.01)))
    factor_a = rng.normal(0.0, 1.0, n)
    factor_b = latent_corr * factor_a + float(np.sqrt(1.0 - latent_corr**2)) * rng.normal(
        0.0, 1.0, n
    )
    method = rng.normal(0.0, 1.0, n)
    columns: dict[str, Any] = {}
    for item in _ITEMS_A:
        columns[item] = (
            loading * factor_a + method_loading * method + noise_sd * rng.normal(0.0, 1.0, n)
        )
    for item in _ITEMS_B:
        columns[item] = (
            loading * factor_b + method_loading * method + noise_sd * rng.normal(0.0, 1.0, n)
        )
    frame = pd.DataFrame(columns)
    frame.index = pd.Index([f"R_{i:04d}" for i in range(1, n + 1)], name="case")
    return frame


def validity_frame(seed: int = 19) -> pd.DataFrame:
    return _two_construct_frame(seed, n=400, latent_corr=0.55, loading=0.75)


def trap_frame(seed: int = 23) -> pd.DataFrame:
    return _two_construct_frame(seed, n=400, latent_corr=0.87, loading=0.92)


def cmb_frame(seed: int = 29, *, with_method: bool = True) -> pd.DataFrame:
    return _two_construct_frame(
        seed,
        n=400,
        latent_corr=0.45,
        loading=0.45,
        method_loading=0.75 if with_method else 0.0,
    )


def two_construct_config() -> dict[str, Any]:
    """A schema-valid contract for the two-construct fixtures."""
    return {
        "schema_version": 1,
        "meta": {
            "study_id": "measurement-fixture-2026",
            "title": "Measurement battery fixture",
            "source_documents": [
                {"role": "study_document", "path": "inputs/m.docx", "sha256": "f" * 64}
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
                    "construct_ref": "FA" if code.startswith("A") else "FB",
                    "scale": {"type": "numeric", "min": -10, "max": 10},
                    "reverse_coded": False,
                    "column_hint": f"Q_{code}",
                }
                for code in (*_ITEMS_A, *_ITEMS_B)
            ]
        },
        "constructs": [
            {
                "code": "FA",
                "name": "Factor A",
                "level": "first_order",
                "measurement": "reflective",
                "indicators": list(_ITEMS_A),
            },
            {
                "code": "FB",
                "name": "Factor B",
                "level": "first_order",
                "measurement": "reflective",
                "indicators": list(_ITEMS_B),
            },
        ],
        "model": {"exogenous": ["FA"], "endogenous": ["FB"]},
        "hypotheses": [
            {"id": "H1", "effect": "direct", "from": "FA", "to": "FB", "sign": "positive"}
        ],
        "data": {"file": "inputs/m.csv", "format": "csv"},
    }
