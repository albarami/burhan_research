"""A priori power (FR-401/403; PB-01; AT-M09-1/2).

Close-fit power is the MacCallum–Browne–Sugawara (1996) noncentral-χ²
procedure: with λ = (N−1)·df·ε², the test of close fit rejects when the
statistic exceeds the (1−α) quantile of χ²(df, λ0), and power is the
survival of χ²(df, λa) at that critical value. Anchored to published
values (Jobst, Bader & Moshagen 2021: df=15, N=200 → 0.378; MacCallum's
minimum-N at df=100 → 132).

The free-parameter count q follows the standard marker-variable
convention, documented here because N:q depends on it (FR-401):

- one loading per first-order construct fixed to 1 → (items − m) free
  loadings, plus one error variance per item;
- one variance (exogenous) or disturbance (endogenous/component) per
  latent, second-order construct included;
- second-order loadings: one per component with the first fixed;
- covariances among exogenous first-level latents: C(k, 2);
- one structural parameter per direct hypothesis (indirect hypotheses
  are functions of direct paths, never parameters).

N:q thresholds come from the governed playbook criterion (PB-01
``n_to_q_target``, "10:1 / 5:1") — parsed, never hard-coded. Below the
floor, :func:`power_gate` emits the Method Advisory through TC-02's
machinery and stops (FR-403: report the shortfall prominently, never
silently proceed).

Monte Carlo power (PB-01, simsem) is escalated: the governed R stack
(04 §: lavaan/semTools/simsem) is not yet in workers/r/renv.lock, and
this module ships no placeholder statistics.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from scipy import stats  # type: ignore[import-untyped]

from burhan.core.errors import IntegrityHalt, halt

if TYPE_CHECKING:
    from burhan.core.advisory import Advisory
    from burhan.core.artifacts.models import StudyConfig
    from burhan.core.playbook import Playbook

_RATIO_RULE = re.compile(r"^\s*(\d+(?:\.\d+)?):1\s*/\s*(\d+(?:\.\d+)?):1\s*$")


def close_fit_power(
    *,
    df: int,
    n: int,
    rmsea0: float = 0.05,
    rmsea_a: float = 0.08,
    alpha: float = 0.05,
) -> float:
    """Power of the RMSEA test of close fit (MacCallum et al. 1996)."""
    if df < 1 or n < 2:
        halt(
            IntegrityHalt(
                "close-fit power requires df >= 1 and N >= 2",
                report={"df": df, "n": n},
            )
        )
    if not 0 < rmsea0 < rmsea_a:
        halt(
            IntegrityHalt(
                "close-fit power requires 0 < rmsea0 < rmsea_a",
                report={"rmsea0": rmsea0, "rmsea_a": rmsea_a},
            )
        )
    lambda0 = (n - 1) * df * rmsea0**2
    lambda_a = (n - 1) * df * rmsea_a**2
    critical = stats.ncx2.ppf(1.0 - alpha, df, lambda0)
    return float(stats.ncx2.sf(critical, df, lambda_a))


def minimum_n_close_fit(
    *,
    df: int,
    target_power: float = 0.80,
    rmsea0: float = 0.05,
    rmsea_a: float = 0.08,
    alpha: float = 0.05,
    n_ceiling: int = 100_000,
) -> int:
    """Smallest N whose close-fit power reaches the target (Table-3 sense)."""
    low, high = 2, n_ceiling

    def power_at(n: int) -> float:
        return close_fit_power(df=df, n=n, rmsea0=rmsea0, rmsea_a=rmsea_a, alpha=alpha)

    if power_at(high) < target_power:
        halt(
            IntegrityHalt(
                "close-fit power target unreachable below the search ceiling",
                report={"df": df, "target_power": target_power, "ceiling": n_ceiling},
            )
        )
    while low < high:
        mid = (low + high) // 2
        if power_at(mid) >= target_power:
            high = mid
        else:
            low = mid + 1
    return low


def free_parameter_count(config: StudyConfig) -> int:
    """Free parameters q under the documented marker-scaling convention."""
    items = config.instrument.items
    first_order = [c for c in config.constructs if c.level == "first_order"]
    second_order = [c for c in config.constructs if c.level == "second_order"]

    loadings = len(items) - len(first_order)
    errors = len(items)

    components: set[str] = set()
    second_order_loadings = 0
    for construct in second_order:
        member = list(construct.components or [])
        components.update(member)
        second_order_loadings += max(len(member) - 1, 0)

    endogenous = set(config.model.endogenous)
    latent_variances = len(first_order) + len(second_order)  # variance or disturbance each

    top_level_exogenous = [
        c.code
        for c in (*first_order, *second_order)
        if c.code not in endogenous and c.code not in components
    ]
    exog_covariances = len(top_level_exogenous) * (len(top_level_exogenous) - 1) // 2

    direct_paths = sum(1 for h in config.hypotheses if h.effect == "direct")

    return (
        loadings
        + errors
        + second_order_loadings
        + latent_variances
        + exog_covariances
        + direct_paths
    )


def model_df(config: StudyConfig) -> int:
    """Degrees of freedom: distinct covariance moments minus q."""
    p = len(config.instrument.items)
    df = p * (p + 1) // 2 - free_parameter_count(config)
    if df < 1:
        halt(
            IntegrityHalt(
                "hypothesized model has no testable degrees of freedom",
                report={"items": p, "q": free_parameter_count(config)},
            )
        )
    return df


def _n_q_thresholds(playbook: Playbook) -> tuple[float, float]:
    """Parse the PB-01 ``n_to_q_target`` criterion value ('10:1 / 5:1')."""
    for criterion in playbook.criteria("PB-01"):
        if criterion.get("name") == "n_to_q_target":
            match = _RATIO_RULE.match(str(criterion.get("value", "")))
            if match is None:
                halt(
                    IntegrityHalt(
                        "PB-01 n_to_q_target value is not parseable as '<target>:1 / <floor>:1'",
                        report={"value": str(criterion.get("value"))},
                    )
                )
            return float(match.group(1)), float(match.group(2))
    halt(
        IntegrityHalt(
            "playbook PB-01 lacks the n_to_q_target criterion",
            report={"criteria": [c.get("name") for c in playbook.criteria("PB-01")]},
        )
    )


def n_q_evaluation(config: StudyConfig, *, n: int, playbook: Playbook) -> dict[str, Any]:
    """N:q against the playbook target and floor (FR-401; PB-01)."""
    target, floor = _n_q_thresholds(playbook)
    q = free_parameter_count(config)
    ratio = n / q
    if ratio >= target:
        status = "meets_target"
    elif ratio >= floor:
        status = "below_target"
    else:
        status = "below_floor"
    return {
        "n": n,
        "q": q,
        "ratio": ratio,
        "target": target,
        "floor": floor,
        "status": status,
    }


def power_gate(
    config: StudyConfig, *, n: int, playbook: Playbook, advisory: Advisory
) -> dict[str, Any]:
    """The a priori power evaluation; below the N:q floor → Method Advisory.

    FR-403: complete what remains defensible, report the shortfall
    prominently; the advisory raise (AdvisoryStop → COMPLETED_TO_BOUNDARY)
    is TC-02's machinery, not a bespoke path.
    """
    df = model_df(config)
    evaluation = n_q_evaluation(config, n=n, playbook=playbook)
    close_fit = close_fit_power(df=df, n=n)
    report = {"df": df, "close_fit_power": close_fit, "n_q": evaluation}
    if evaluation["status"] == "below_floor":
        criterion = next(c for c in playbook.criteria("PB-01") if c.get("name") == "n_to_q_target")
        citations = [
            f"{key}: {playbook.citation(key)}" for key in criterion.get("citation_keys", [])
        ]
        advisory.emit(
            stage="power",
            trigger="N:q below the absolute floor (PB-01)",
            diagnostics={
                "n": n,
                "q": evaluation["q"],
                "ratio": round(float(evaluation["ratio"]), 4),
                "floor": evaluation["floor"],
                "target": evaluation["target"],
                "close_fit_power": round(close_fit, 4),
                "df": df,
            },
            recommendation=(
                "Collect additional responses before estimation: the sample "
                "cannot support the hypothesized free-parameter count at the "
                "playbook floor (N:q >= "
                f"{evaluation['floor']:.0f}:1). Proceeding would not be "
                "defensible under the approved method."
            ),
            citations=citations,
            impact=(
                "Estimation stages are not run; the package completes to the "
                "defensible boundary with this advisory as the record."
            ),
        )
    return report


def power_store_rows(
    config: StudyConfig, *, n: int, playbook: Playbook, created: str
) -> list[dict[str, Any]]:
    """Schema-valid results-store rows under the PB-01 output prefixes."""
    df = model_df(config)
    evaluation = n_q_evaluation(config, n=n, playbook=playbook)
    close_fit = close_fit_power(df=df, n=n)
    common = {
        "schema_version": 1,
        "stage": "power",
        "engine": "py_pandas",
        "playbook_step": "PB-01",
        "created": created,
        "hash": "0" * 64,
    }
    return [
        {
            **common,
            "id": "power.close_fit.estimate",
            "value": round(close_fit, 6),
            "params": {"df": df, "n": n, "rmsea0": 0.05, "rmsea_a": 0.08, "alpha": 0.05},
        },
        {
            **common,
            "id": "power.n_to_q.ratio",
            "value": round(float(evaluation["ratio"]), 6),
            "n": n,
            "params": {
                "q": evaluation["q"],
                "target": evaluation["target"],
                "floor": evaluation["floor"],
                "status": evaluation["status"],
            },
        },
    ]
