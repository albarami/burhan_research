"""Store-row serialization for the Stage-1A adapters (TC-15, D4).

Turns each certified module's result into append-only results-store rows whose
``id`` families match the playbook ``outputs`` a stage must evidence to mark its
steps ``completed``. Four families already have helpers in ``burhan.stats``
(power, assumptions — which embed store-owned fields; effects, robustness —
clean); the rest (power.montecarlo, prep, assumptions collinearity/estimator,
all of measurement and structural) are hand-written here. No statistics are
computed — this is pure projection of already-certified results (D4). Rows may
carry store-owned fields from the wrapped helpers; :func:`context.store_row`
strips them before write.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from burhan.stats.assumptions import assumptions_store_rows
from burhan.stats.effects import effects_store_rows
from burhan.stats.power import power_store_rows
from burhan.stats.robustness import robustness_store_rows

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    import pandas as pd  # type: ignore[import-untyped]

    from burhan.core.artifacts.models import StudyConfig
    from burhan.prep.py_impl.pipeline import PrepResult

_R = "r_lavaan"
_PY = "py_pandas"

# The wrapped helpers require a ``created`` they embed for their jsonschema
# path; the store owns ``created`` and re-injects it, so the value is discarded.
_DISCARDED_TS = "1970-01-01T00:00:00Z"


def _row(
    stat_id: str,
    value: bool | int | float | str,
    *,
    stage: str,
    step: str,
    engine: str,
    **optional: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": stat_id,
        "value": value,
        "stage": stage,
        "engine": engine,
        "playbook_step": step,
    }
    row.update({key: val for key, val in optional.items() if val is not None})
    return row


# -- power (PB-01) -----------------------------------------------------------


def power_rows(
    config: StudyConfig, *, n: int, playbook: Any, montecarlo: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """power.close_fit + power.n_to_q (helper) plus power.montecarlo (hand-written)."""
    rows = list(power_store_rows(config, n=n, playbook=playbook, created=_DISCARDED_TS))
    powers = [float(v) for v in montecarlo["power"].values()]
    rows.append(
        _row(
            "power.montecarlo",
            min(powers) if powers else 0.0,
            stage="power",
            step="PB-01",
            engine=_R,
            n=int(montecarlo["n"]),
            params={
                "replications": int(montecarlo["replications"]),
                "converged": int(montecarlo["converged"]),
                "power": dict(montecarlo["power"]),
            },
        )
    )
    return rows


# -- prep (PB-02..04) --------------------------------------------------------


def prep_rows(prep: PrepResult) -> list[dict[str, Any]]:
    chain = prep.n_chain
    screened = sum(len(entries) for entries in prep.screening.values())
    return [
        _row(
            "prep.n_chain",
            chain.final_n,
            stage="prep",
            step="PB-02",
            engine=_PY,
            n=chain.final_n,
            params={"raw_n": chain.raw_n, "final_n": chain.final_n},
        ),
        _row("prep.screening", screened, stage="prep", step="PB-02", engine=_PY),
        _row(
            "prep.missingness",
            str(prep.missingness["mechanism_verdict"]),
            stage="prep",
            step="PB-03",
            engine=_PY,
            params={"treatment": prep.missingness["treatment"]["method"]},
        ),
        _row(
            "prep.outliers",
            len(prep.outliers["flagged"]),
            stage="prep",
            step="PB-04",
            engine=_PY,
        ),
    ]


# -- assumptions (PB-05..07) -------------------------------------------------


def assumptions_rows(
    frame: pd.DataFrame, *, playbook: Any, vif: Mapping[str, Any], estimator: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """assumptions.normality (helper) plus collinearity + estimator (hand-written)."""
    rows = list(assumptions_store_rows(frame, playbook=playbook, created=_DISCARDED_TS))
    max_vif = max((float(c["vif"]) for c in vif["composites"]), default=0.0)
    rows.append(
        _row(
            "assumptions.collinearity",
            max_vif,
            stage="assumptions",
            step="PB-06",
            engine=_PY,
            params={"composites": len(vif["composites"])},
        )
    )
    rows.append(
        _row(
            "assumptions.estimator",
            str(estimator["estimator"]),
            stage="assumptions",
            step="PB-07",
            engine=_PY,
            params={"basis": estimator["basis"], "rule_id": estimator["rule_id"]},
        )
    )
    return rows


# -- measurement (PB-08..11, 13) ---------------------------------------------


def measurement_rows(
    measurement: Mapping[str, Any], deletion: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """spec/loadings/reliability/convergent/discriminant + item_deletion.

    PB-12 (cmb) and PB-14 (respecification) are recorded ``flagged`` by the
    adapter (no marker; adequate fit), so they emit no rows here.
    """
    rows: list[dict[str, Any]] = [
        _row(
            "measurement.spec",
            str(measurement["approach"]),
            stage="measurement",
            step="PB-08",
            engine=_R,
        )
    ]
    for loading in measurement["first_order"]["loadings"]:
        rows.append(
            _row(
                f"measurement.loadings.{loading['item']}",
                float(loading["std"]),
                stage="measurement",
                step="PB-08",
                engine=_R,
                se=float(loading["se"]),
                p=_clamp_p(loading.get("p")),
            )
        )
    for rel in measurement["first_order"]["reliability"]:
        rows.append(
            _row(
                f"measurement.reliability.{rel['construct']}",
                float(rel["cr"]),
                stage="measurement",
                step="PB-10",
                engine=_R,
                params={"alpha": float(rel["alpha"])},
            )
        )
        rows.append(
            _row(
                f"measurement.convergent.{rel['construct']}",
                float(rel["ave"]),
                stage="measurement",
                step="PB-10",
                engine=_R,
            )
        )
    for pair in measurement["validity"]["htmt"]["pairs"]:
        rows.append(
            _row(
                f"measurement.discriminant.{pair['a']}_{pair['b']}",
                float(pair["value"]),
                stage="measurement",
                step="PB-11",
                engine=_R,
            )
        )
    rows.append(
        _row(
            "measurement.item_deletion",
            len(deletion["candidates"]),
            stage="measurement",
            step="PB-13",
            engine=_R,
            params={"mode": deletion["mode"], "deletions": len(deletion["deletions"])},
        )
    )
    return rows


# -- structural (PB-15..16) --------------------------------------------------


def structural_rows(structural: Mapping[str, Any]) -> list[dict[str, Any]]:
    fit = structural["fit"]
    rows: list[dict[str, Any]] = [
        _row(
            f"structural.fit.{index}",
            float(fit[index]),
            stage="structural",
            step="PB-15",
            engine=_R,
        )
        for index in ("chisq", "cfi", "tli", "rmsea", "srmr")
    ]
    for path in structural["paths"]:
        rows.append(
            _row(
                f"structural.path.{path['rhs']}->{path['lhs']}",
                float(path["est"]),
                stage="structural",
                step="PB-16",
                engine=_R,
                se=float(path["se"]),
                p=_clamp_p(path.get("p")),
            )
        )
    for r2 in structural["r_squared"]:
        rows.append(
            _row(
                f"structural.r_squared.{r2['construct']}",
                float(r2["r2"]),
                stage="structural",
                step="PB-16",
                engine=_R,
            )
        )
    return rows


# -- effects (PB-17) / robustness (PB-18..19): clean helpers, used as-is ------


def effects_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    return list(effects_store_rows(report))


def robustness_rows(
    alternatives: Mapping[str, Any], achieved_power: Mapping[str, Any]
) -> list[dict[str, Any]]:
    return list(robustness_store_rows(alternatives, achieved_power))


def _clamp_p(value: Any) -> float | None:
    """A p in [0, 1] as the store validates; None passes through unset."""
    if value is None:
        return None
    return min(1.0, max(0.0, float(value)))


def loading_sequence(measurement: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    """The first-order loadings (helper for adapter provenance/assertions)."""
    loadings: Sequence[Mapping[str, Any]] = measurement["first_order"]["loadings"]
    return loadings
