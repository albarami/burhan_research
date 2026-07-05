"""Realistic CB-SEM integration study (TC-15, D3 separate integration builder).

The golden defect-detection twin draws INDEPENDENT per-construct latents, so
its fitted 3-factor model reproduces the covariance matrix near-exactly
(rmsea 0.0) — a degenerate perfect fit with no modification indices and no
mediation. That twin certifies prep (M08); it cannot exercise the structural
half of the pipeline.

This study instead has a real causal chain ``RES -> CUL -> INT`` with moderate
effects, an explicit indirect hypothesis (H3), and an adequately-powered N, so
a full 13-stage run exercises power, measurement, structural, effects
(mediation decomposition), and robustness end-to-end. Determinism is inherited
from ``generator`` (injected seed, no ambient RNG). The study carries no method
marker — the StudyConfig schema designates none — so PB-12 CMB is recorded
``flagged`` per the playbook's ``failure_action: flag``.

Generative parameters are fixture-scoped design choices (D3): moderate loadings
(construct SDs vs. item residual) put standardized loadings near the ~0.7 CFA
target; the two paths sit at ~0.4–0.5 so the mediation is substantive without
saturating fit.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

import numpy as np
from generator import (
    _CONSTRUCTS,
    _ITEMS,
    DEFECT_CLASSES,
    GoldenStudy,
    _case_row,
    _config_dict,
    _header_rows,
    _stored,
)

if TYPE_CHECKING:
    from numpy.random import Generator

# Study size: comfortably above the 5:1 N:q floor for the ~38-free-parameter
# model, so a-priori power flags-or-passes but never trips the advisory boundary.
_N_DEFAULT = 300

# Causal path magnitudes (latent regression coefficients) and dispersion. INT is
# a PARTIAL mediation of RES through CUL: it carries both a direct RES effect and
# the CUL-mediated indirect one, so the effects stage yields direct + indirect +
# total (the total exists only when the mediated pair also has a direct edge).
_BETA_CUL_RES = 0.45
_BETA_INT_CUL = 0.45
_BETA_INT_RES = 0.25  # direct RES -> INT (partial mediation)
_EXO_SD = 0.70  # RES latent dispersion
_DISTURBANCE_SD = 0.55  # CUL/INT structural disturbance
_ITEM_RESIDUAL_SD = 0.45  # per-indicator measurement error

# Partial-mediation hypotheses added to the golden H1 (RES->CUL) / H2 (CUL->INT).
_ADDED_HYPOTHESES: list[dict[str, Any]] = [
    {"id": "H3", "effect": "direct", "from": "RES", "to": "INT", "sign": "positive"},
    {
        "id": "H4",
        "effect": "indirect",
        "from": "RES",
        "to": "INT",
        "sign": "positive",
        "via": ["CUL"],
    },
]


def integration_config() -> dict[str, Any]:
    """The golden contract, retargeted with the partial-mediation hypotheses."""
    config = copy.deepcopy(_config_dict())
    config["meta"]["study_id"] = "integration-adoption-2026"
    config["meta"]["title"] = "Realistic CB-SEM integration study (TC-15)"
    config["data"]["file"] = "inputs/integration.csv"
    config["hypotheses"].extend(_ADDED_HYPOTHESES)
    return config


def _causal_item_values(rng: Generator) -> list[int]:
    """One case's responses from a partial-mediation RES -> CUL -> INT chain."""
    res = float(rng.normal(0.0, _EXO_SD))
    cul = _BETA_CUL_RES * res + float(rng.normal(0.0, _DISTURBANCE_SD))
    inte = _BETA_INT_CUL * cul + _BETA_INT_RES * res + float(rng.normal(0.0, _DISTURBANCE_SD))
    latents = {"RES": res, "CUL": cul, "INT": inte}
    values: list[int] = []
    for _code, construct, _hint, _reverse in _ITEMS:
        value = 4.0 + latents[construct] + float(rng.normal(0.0, _ITEM_RESIDUAL_SD))
        values.append(int(np.clip(round(value), 1, 7)))
    return values


def build_integration_study(seed: int, *, n: int = _N_DEFAULT) -> GoldenStudy:
    """A clean, adequately-powered, mediation-bearing study (no planted defects)."""
    rng = np.random.default_rng(seed)
    manifest: dict[str, list[dict[str, str]]] = {name: [] for name in DEFECT_CLASSES}
    rows = _header_rows()
    for index in range(1, n + 1):
        stored = _stored(_causal_item_values(rng), un_reverse_cu4=False)
        rows.append(_case_row(f"R_{index:03d}", stored, rng))
    assert set(_CONSTRUCTS) == {"RES", "CUL", "INT"}  # latent chain matches the contract
    return GoldenStudy(config=integration_config(), rows=rows, manifest=manifest)
