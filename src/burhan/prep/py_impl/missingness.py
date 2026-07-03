"""Missingness mechanism testing and policy-driven treatment (FR-503/504).

Little's MCAR test (Little 1988, JASA 83:1198–1202): cases grouped by
missingness pattern; the statistic is

    d² = Σ_j n_j (ȳ_j − μ̂_[O_j])ᵀ Σ̂_[O_j,O_j]⁻¹ (ȳ_j − μ̂_[O_j])

with μ̂/Σ̂ the EM (MVN) estimates and df = Σ_j |O_j| − p, referred to the
χ² distribution. MCAR is never *confirmed* — only not rejected; and a
rejection cannot separate MAR from MNAR, so a rejection keeps the
MAR-appropriate policy primary and raises the MNAR sensitivity flag per
``prep.missing_treatment.mnar_action`` (PB-03: failure_action flag).

The α for the rejection decision is an explicit parameter (default .05,
the discipline's convention — the playbook/policy define no MCAR alpha);
every treatment choice reads policy paths. This module never fills a
cell: FIML/MI happen at estimation, preparation only selects and logs
(FR-505). Reports carry patterns, counts, and case IDs — never values.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

# Untyped third-party edge (no stubs in the locked dependency set).
from scipy import stats  # type: ignore[import-untyped]

from burhan.core.errors import IntegrityHalt, halt

if TYPE_CHECKING:
    # Untyped third-party edge (no stubs in the locked dependency set).
    import pandas as pd  # type: ignore[import-untyped]

    from burhan.core.policy import Policy

_EM_MAX_ITER = 200
_EM_TOL = 1e-6
_RIDGE = 1e-8


def _em_mean_cov(data: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """EM estimates of the MVN mean and covariance under MAR."""
    n, p = data.shape
    observed = ~np.isnan(data)
    mean = np.nanmean(data, axis=0)
    centered = np.where(observed, data - mean, 0.0)
    cov = (centered.T @ centered) / n + np.eye(p) * _RIDGE
    for _ in range(_EM_MAX_ITER):
        filled = np.where(observed, data, 0.0)
        correction = np.zeros((p, p))
        for row in range(n):
            missing = ~observed[row]
            if not missing.any():
                continue
            obs = observed[row]
            solve = np.linalg.solve(
                cov[np.ix_(obs, obs)] + np.eye(int(obs.sum())) * _RIDGE,
                data[row, obs] - mean[obs],
            )
            filled[row, missing] = mean[missing] + cov[np.ix_(missing, obs)] @ solve
            conditional = cov[np.ix_(missing, missing)] - cov[np.ix_(missing, obs)] @ (
                np.linalg.solve(
                    cov[np.ix_(obs, obs)] + np.eye(int(obs.sum())) * _RIDGE,
                    cov[np.ix_(obs, missing)],
                )
            )
            correction[np.ix_(missing, missing)] += conditional
        new_mean = filled.mean(axis=0)
        centered = filled - new_mean
        new_cov = (centered.T @ centered + correction) / n + np.eye(p) * _RIDGE
        shift = float(np.max(np.abs(new_mean - mean)) + np.max(np.abs(new_cov - cov)))
        mean, cov = new_mean, new_cov
        if shift < _EM_TOL:
            break
    return mean, cov


def littles_mcar(frame: pd.DataFrame) -> tuple[float, int, float]:
    """Little's MCAR test: (d², df, p). Complete data passes degenerately."""
    data = frame.to_numpy(dtype=float)
    observed = ~np.isnan(data)
    p_items = data.shape[1]
    patterns: dict[tuple[bool, ...], list[int]] = {}
    for row in range(data.shape[0]):
        patterns.setdefault(tuple(observed[row]), []).append(row)
    incomplete = {k: v for k, v in patterns.items() if not all(k)}
    if not incomplete:
        return 0.0, 0, 1.0
    mean, cov = _em_mean_cov(data)
    d2 = 0.0
    df = 0
    for pattern, rows in sorted(patterns.items(), reverse=True):
        mask = np.array(pattern)
        if not mask.any():
            continue
        group = data[np.ix_(rows, np.flatnonzero(mask))]
        deviation = group.mean(axis=0) - mean[mask]
        solve = np.linalg.solve(
            cov[np.ix_(mask, mask)] + np.eye(int(mask.sum())) * _RIDGE, deviation
        )
        d2 += len(rows) * float(deviation @ solve)
        df += int(mask.sum())
    df -= p_items
    p_value = float(stats.chi2.sf(d2, df)) if df > 0 else 1.0
    return float(d2), df, p_value


def _pattern_map(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Missingness patterns with counts — computed before any treatment."""
    groups: dict[tuple[str, ...], int] = {}
    for _, row in frame.iterrows():
        missing = tuple(sorted(code for code in frame.columns if np.isnan(row[code])))
        groups[missing] = groups.get(missing, 0) + 1
    return [
        {"missing_items": list(missing), "n": count}
        for missing, count in sorted(groups.items(), key=lambda item: (len(item[0]), item[0]))
    ]


def missingness_report(
    frame: pd.DataFrame,
    policy: Policy,
    *,
    alpha: float = 0.05,
    select: str = "primary",
) -> dict[str, Any]:
    """Mechanism evidence first, then the policy-driven treatment (FR-503).

    ``select`` names which policy slot supplies the treatment — the fixed
    ``primary`` (fiml, FR-504) or the policy-selectable ``alternative``.
    The method itself and its parameters are read from policy paths; a
    method outside the known-safe set halts (FR-505: mean substitution has
    no code path, even under a doctored policy object).
    """
    d2, df, p_value = littles_mcar(frame)
    verdict = "mcar_not_rejected" if p_value > alpha else "mcar_rejected"
    report: dict[str, Any] = {
        "pattern_map": _pattern_map(frame),
        "little_mcar": {"d2": round(d2, 6), "df": df, "p": round(p_value, 6)},
        "mechanism_verdict": verdict,
    }
    if select not in ("primary", "alternative"):
        halt(
            IntegrityHalt(
                "unknown missing-data treatment selector",
                report={"select": select},
            )
        )
    method = str(policy.rule(f"prep.missing_treatment.{select}"))
    if method == "fiml":
        treatment: dict[str, Any] = {"method": "fiml", "params": {}}
    elif method == "multiple_imputation":
        treatment = {
            "method": "multiple_imputation",
            "params": {
                "imputations": int(policy.rule("prep.missing_treatment.mi_imputations")),
                "pooling": "rubin_rules",
            },
        }
    else:
        halt(
            IntegrityHalt(
                "unknown missing-data treatment in policy (FR-504/505)",
                report={"select": select, "method": method},
            )
        )
    treatment["rationale"] = f"policy {select} '{method}' under mechanism verdict '{verdict}'"
    treatment["mnar_flag"] = False
    if verdict == "mcar_rejected":
        action = str(policy.rule("prep.missing_treatment.mnar_action"))
        treatment["mnar_flag"] = True
        if action == "flag_with_sensitivity_note":
            treatment["sensitivity_note"] = (
                "Little's test rejected MCAR; MAR is assumed for the primary "
                "treatment and MNAR cannot be excluded — report a sensitivity "
                "analysis alongside the primary results."
            )
    report["treatment"] = treatment
    return report
