"""Distributional/collinearity diagnostics and estimator determination
(FR-601–603; PB-05/06/07; AT-M09-3/4).

Mardia (1970) coefficients with the biased (divisor-n) covariance — the
convention psych/MVN use, anchored to the published setosa values
(Korkmaz et al. 2014, The R Journal 6(2):151–162): b1p = 3.0797
(p = .1772), b2p = 26.5377 (p = .1953). Univariate skewness/kurtosis are
the population-moment estimators (kurtosis as excess); band limits come
from the governed playbook criterion (PB-05 ``univariate_bands``,
"2 / 7"), never code literals.

The estimator determination (PB-07) is evidence → policy, in order:

1. categories < 5 (policy ``estimator.wlsmv_conditions``) or severe
   non-normality beyond the policy skew/kurtosis bounds → WLSMV on
   polychoric correlations;
2. otherwise Mardia violation (either test significant at α) → MLR
   (policy ``estimator.robust_trigger.on_mardia_violation``);
3. otherwise the policy default (ML).

Every determination appends a DecisionEntry through TC-02's policy
engine — stage ``assumptions``, decision point
``estimator_determination``, the governed thresholds recorded in
``inputs``, full citation strings resolved through the playbook (FR-603).
Artifacts carry statistics and case IDs only, never respondent values.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import numpy as np
from scipy import stats  # type: ignore[import-untyped]

from burhan.core.errors import IntegrityHalt, halt

if TYPE_CHECKING:
    import pandas as pd  # type: ignore[import-untyped]

    from burhan.core.playbook import Playbook
    from burhan.core.policy import DecisionLog, Policy

_BANDS_RULE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*$")


def _bands(playbook: Playbook) -> tuple[float, float]:
    """Parse PB-05 ``univariate_bands`` ('2 / 7') from the playbook."""
    for criterion in playbook.criteria("PB-05"):
        if criterion.get("name") == "univariate_bands":
            match = _BANDS_RULE.match(str(criterion.get("value", "")))
            if match is None:
                halt(
                    IntegrityHalt(
                        "PB-05 univariate_bands value is not parseable as '<skew> / <kurtosis>'",
                        report={"value": str(criterion.get("value"))},
                    )
                )
            return float(match.group(1)), float(match.group(2))
    halt(
        IntegrityHalt(
            "playbook PB-05 lacks the univariate_bands criterion",
            report={"criteria": [c.get("name") for c in playbook.criteria("PB-05")]},
        )
    )


def univariate_moments(frame: pd.DataFrame, *, playbook: Playbook) -> dict[str, Any]:
    """Per-item skewness and excess kurtosis against the playbook bands."""
    skew_limit, kurtosis_limit = _bands(playbook)
    entries: list[dict[str, Any]] = []
    for column in frame.columns:
        values = frame[column].dropna().to_numpy(dtype=float)
        if len(values) < 3 or float(np.var(values)) == 0.0:
            halt(
                IntegrityHalt(
                    "univariate moments need at least 3 varying observations",
                    report={"item": str(column), "n": int(len(values))},
                )
            )
        centered = values - values.mean()
        m2 = float((centered**2).mean())
        skewness = float((centered**3).mean()) / m2**1.5
        kurtosis = float((centered**4).mean()) / m2**2 - 3.0
        entries.append(
            {
                "item": str(column),
                "n": int(len(values)),
                "skewness": skewness,
                "kurtosis": kurtosis,
                "within_bands": abs(skewness) < skew_limit and abs(kurtosis) < kurtosis_limit,
            }
        )
    return {"skew_limit": skew_limit, "kurtosis_limit": kurtosis_limit, "items": entries}


def mardia(frame: pd.DataFrame) -> dict[str, Any]:
    """Mardia's multivariate skewness/kurtosis (1970), psych/MVN convention."""
    data = frame.dropna().to_numpy(dtype=float)
    n, p = data.shape if data.ndim == 2 else (0, 0)
    if n <= p or p < 2:
        halt(
            IntegrityHalt(
                "Mardia's test needs more complete cases than variables "
                "(and at least two variables)",
                report={"n": int(n), "p": int(p)},
            )
        )
    centered = data - data.mean(axis=0)
    covariance = centered.T @ centered / n  # biased, divisor n (Mardia 1970)
    try:
        inverse = np.linalg.inv(covariance)
    except np.linalg.LinAlgError:
        halt(
            IntegrityHalt(
                "covariance matrix is singular; Mardia's test undefined",
                report={"n": int(n), "p": int(p)},
            )
        )
    gram = centered @ inverse @ centered.T
    b1p = float((gram**3).sum()) / n**2
    b2p = float((np.diag(gram) ** 2).sum()) / n
    skew_statistic = n * b1p / 6.0
    skew_df = p * (p + 1) * (p + 2) / 6.0
    skew_p = float(stats.chi2.sf(skew_statistic, skew_df))
    kurtosis_z = (b2p - p * (p + 2)) / float(np.sqrt(8.0 * p * (p + 2) / n))
    kurtosis_p = float(2.0 * stats.norm.sf(abs(kurtosis_z)))
    return {
        "n": int(n),
        "p": int(p),
        "b1p": b1p,
        "skew_statistic": skew_statistic,
        "skew_df": skew_df,
        "skew_p": skew_p,
        "b2p": b2p,
        "kurtosis_z": kurtosis_z,
        "kurtosis_p": kurtosis_p,
    }


def vif_composites(frame: pd.DataFrame) -> dict[str, Any]:
    """VIF/tolerance across composites (PB-06): VIF_j = 1 / (1 − R²_j)."""
    columns = list(frame.columns)
    if len(columns) < 2:
        halt(
            IntegrityHalt(
                "collinearity diagnostics need at least two composites",
                report={"composites": [str(c) for c in columns]},
            )
        )
    data = frame.dropna().to_numpy(dtype=float)
    entries: list[dict[str, Any]] = []
    for index, name in enumerate(columns):
        response = data[:, index]
        predictors = np.delete(data, index, axis=1)
        design = np.column_stack([np.ones(len(predictors)), predictors])
        coefficients, *_ = np.linalg.lstsq(design, response, rcond=None)
        fitted = design @ coefficients
        total = float(((response - response.mean()) ** 2).sum())
        residual = float(((response - fitted) ** 2).sum())
        r_squared = 1.0 - residual / total if total > 0 else 0.0
        vif = float("inf") if r_squared >= 1.0 else 1.0 / (1.0 - r_squared)
        entries.append(
            {
                "composite": str(name),
                "r_squared": r_squared,
                "vif": vif,
                "tolerance": 0.0 if vif == float("inf") else 1.0 / vif,
            }
        )
    return {"composites": entries}


def mahalanobis_feed(frame: pd.DataFrame, *, policy: Policy) -> dict[str, Any]:
    """Complete-case D² at the policy criterion (FR-601 feed)."""
    criterion_p = float(policy.rule("prep.outliers.mahalanobis_p"))
    complete = frame.dropna()
    data = complete.to_numpy(dtype=float)
    if data.shape[0] <= data.shape[1]:
        halt(
            IntegrityHalt(
                "Mahalanobis feed needs more complete cases than variables",
                report={"n": int(data.shape[0]), "p": int(data.shape[1])},
            )
        )
    centered = data - data.mean(axis=0)
    covariance = np.cov(centered, rowvar=False)
    inverse = np.linalg.pinv(covariance)
    d2 = np.einsum("ij,jk,ik->i", centered, inverse, centered)
    criterion = float(stats.chi2.ppf(1.0 - criterion_p, df=data.shape[1]))
    flagged = [
        str(case) for case, value in zip(complete.index, d2, strict=True) if value > criterion
    ]
    return {
        "criterion_p": criterion_p,
        "criterion_d2": criterion,
        "d2": {str(case): float(value) for case, value in zip(complete.index, d2, strict=True)},
        "flagged_cases": flagged,
    }


def assumptions_store_rows(
    frame: pd.DataFrame, *, playbook: Playbook, created: str
) -> list[dict[str, Any]]:
    """Schema-valid rows under the PB-05 output prefix (``assumptions.*``)."""
    result = mardia(frame)
    moments = univariate_moments(frame, playbook=playbook)
    worst_skew = max(abs(e["skewness"]) for e in moments["items"])
    worst_kurtosis = max(abs(e["kurtosis"]) for e in moments["items"])
    common = {
        "schema_version": 1,
        "stage": "assumptions",
        "engine": "py_pandas",
        "playbook_step": "PB-05",
        "created": created,
        "hash": "0" * 64,
    }
    return [
        {
            **common,
            "id": "assumptions.normality.mardia_skew_p",
            "value": round(result["skew_p"], 6),
            "params": {"b1p": round(result["b1p"], 6), "df": result["skew_df"]},
        },
        {
            **common,
            "id": "assumptions.normality.mardia_kurtosis_p",
            "value": round(result["kurtosis_p"], 6),
            "params": {"b2p": round(result["b2p"], 6), "z": round(result["kurtosis_z"], 6)},
        },
        {
            **common,
            "id": "assumptions.normality.max_abs_skewness",
            "value": round(worst_skew, 6),
            "params": {"limit": moments["skew_limit"]},
        },
        {
            **common,
            "id": "assumptions.normality.max_abs_kurtosis",
            "value": round(worst_kurtosis, 6),
            "params": {"limit": moments["kurtosis_limit"]},
        },
    ]


def _observed_categories(frame: pd.DataFrame) -> int:
    values = frame.dropna().to_numpy(dtype=float)
    return int(len(np.unique(values)))


def estimator_determination(
    frame: pd.DataFrame,
    *,
    policy: Policy,
    playbook: Playbook,
    decision_log: DecisionLog,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """PB-07: select the estimator from evidence; log rationale (FR-603)."""
    max_categorical = int(policy.rule("estimator.wlsmv_conditions.max_categories_for_categorical"))
    severe_skew = float(policy.rule("estimator.wlsmv_conditions.severe_skew_abs"))
    severe_kurtosis = float(policy.rule("estimator.wlsmv_conditions.severe_kurtosis_abs"))
    robust = str(policy.rule("estimator.robust_trigger.on_mardia_violation"))
    default = str(policy.rule("estimator.default"))

    categories = _observed_categories(frame)
    moments = univariate_moments(frame, playbook=playbook)
    worst_skew = max(abs(e["skewness"]) for e in moments["items"])
    worst_kurtosis = max(abs(e["kurtosis"]) for e in moments["items"])
    mardia_result = mardia(frame)
    mardia_violation = mardia_result["skew_p"] < alpha or mardia_result["kurtosis_p"] < alpha

    criteria = {c.get("name"): c for c in playbook.criteria("PB-07")}

    def citations_for(name: str) -> list[str]:
        keys = criteria.get(name, {}).get("citation_keys", [])
        return [f"{key}: {playbook.citation(key)}" for key in keys]

    inputs: dict[str, Any] = {
        "categories": categories,
        "max_categories_for_categorical": max_categorical,
        "max_abs_skewness": round(worst_skew, 4),
        "max_abs_kurtosis": round(worst_kurtosis, 4),
        "severe_skew_abs": severe_skew,
        "severe_kurtosis_abs": severe_kurtosis,
        "mardia_skew_p": round(mardia_result["skew_p"], 6),
        "mardia_kurtosis_p": round(mardia_result["kurtosis_p"], 6),
        "mardia_violation": mardia_violation,
        "alpha": alpha,
    }

    if (
        categories <= max_categorical
        or worst_skew >= severe_skew
        or worst_kurtosis >= severe_kurtosis
    ):
        estimator = "wlsmv"
        basis = "polychoric"
        rule_id = "estimator.wlsmv_conditions"
        rationale = (
            f"{categories} observed response categories (categorical at "
            f"<= {max_categorical}) or severity beyond the policy bounds: "
            "ordinal indicators are never treated as continuous by default "
            "(FR-602); WLSMV on polychoric correlations."
        )
        citations = citations_for("categorical_path")
    elif mardia_violation:
        estimator = robust
        basis = "covariance"
        rule_id = "estimator.robust_trigger.on_mardia_violation"
        rationale = (
            "Univariate bands hold and categories permit continuous "
            "treatment, but Mardia's test rejects multivariate normality "
            f"(skew p={mardia_result['skew_p']:.4g}, kurtosis "
            f"p={mardia_result['kurtosis_p']:.4g}): robust ML with "
            "Satorra-Bentler corrections (within-method, autonomous)."
        )
        citations = citations_for("robust_adjustment")
    else:
        estimator = default
        basis = "covariance"
        rule_id = "estimator.default"
        rationale = (
            f"{categories} response categories (>= {max_categorical + 1}), "
            "univariate bands hold, and Mardia's test does not reject "
            "multivariate normality: maximum likelihood under the policy "
            "default."
        )
        citations = citations_for("continuous_conditions")

    decision_log.append(
        {
            "stage": "assumptions",
            "decision_point": "estimator_determination",
            "rule_id": rule_id,
            "rule_version": policy.version,
            "inputs": inputs,
            "decision": estimator,
            "rationale": rationale,
        }
    )
    return {
        "estimator": estimator,
        "basis": basis,
        "rule_id": rule_id,
        "rationale": rationale,
        "citations": citations,
        "inputs": inputs,
    }
