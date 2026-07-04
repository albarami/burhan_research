"""Alternative-model comparison and achieved power (FR-901/402; PB-18/19).

The canonical rival reverses the declared direct paths ("theoretically
motivated alternative structure": the causal direction is the standard
contested choice). Each alternative is estimated through the same
structural lane as the retained model and compared on fit plus
information-criterion deltas. With one dataset, ΔAIC and ΔBIC follow
exactly from chi-square and free-parameter counts — Δχ² + 2·Δk and
Δχ² + ln(N)·Δk — because the saturated log-likelihood cancels; no
placeholder statistic is involved. A preferred alternative flags
(PB-18 failure_action). Achieved power closes the PB-01 loop with the
certified close-fit machinery at the final analytical N (PB-19).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeGuard

from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig
from burhan.core.errors import IntegrityHalt, halt
from burhan.stats.power import close_fit_power, model_df
from burhan.stats.structural import run_structural

if TYPE_CHECKING:
    import pandas as pd  # type: ignore[import-untyped]

    from burhan.core.playbook import Playbook
    from burhan.core.rworker import RWorker


def _is_number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def alternative_floor(playbook: Playbook) -> int:
    """PB-18: the governed minimum number of alternative models (>= 1)."""
    for criterion in playbook.criteria("PB-18"):
        if criterion.get("name") != "alternative_required":
            continue
        value = criterion.get("value")
        if (
            not _is_number(value)
            or not math.isfinite(value)
            or int(value) != value
            or int(value) < 1
        ):
            break
        return int(value)
    halt(
        IntegrityHalt(
            "PB-18 does not state an integer alternative floor of at least 1",
            report={"step": "PB-18", "criterion": "alternative_required"},
        )
    )


def power_floor(playbook: Playbook) -> float:
    """PB-19: the governed achieved power floor."""
    for criterion in playbook.criteria("PB-19"):
        if criterion.get("name") != "achieved_power_report":
            continue
        value = criterion.get("value")
        if not _is_number(value) or not 0.0 < value < 1.0:
            break
        return float(value)
    halt(
        IntegrityHalt(
            "PB-19 does not state a numeric achieved power floor",
            report={"step": "PB-19", "criterion": "achieved_power_report"},
        )
    )


def reversed_alternative(config: StudyConfig) -> StudyConfig:
    """The canonical rival: every declared direct path reversed."""
    data = config.model_dump(mode="python", exclude_none=True, by_alias=True)
    reversed_hypotheses = []
    for hypothesis in data["hypotheses"]:
        if hypothesis["effect"] != "direct":
            continue
        reversed_hypotheses.append(
            {**hypothesis, "from": hypothesis["to"], "to": hypothesis["from"]}
        )
    if not reversed_hypotheses:
        halt(
            IntegrityHalt(
                "the contract declares no direct path to reverse",
                report={"hypotheses": len(data["hypotheses"])},
            )
        )
    data["hypotheses"] = reversed_hypotheses
    data["model"] = {
        **data["model"],
        "exogenous": data["model"]["endogenous"],
        "endogenous": data["model"]["exogenous"],
    }
    return validate_and_build(StudyConfig, data)


def _complete_n(frame: pd.DataFrame, config: StudyConfig) -> int:
    items = [item.code for item in config.instrument.items if item.code in frame.columns]
    return int(len(frame[items].dropna()))


def run_alternatives(
    frame: pd.DataFrame,
    config: StudyConfig,
    *,
    playbook: Playbook,
    rworker: RWorker,
    run_dir: Any,
    call_id: str,
    alternatives: list[tuple[str, StudyConfig]] | None = None,
) -> dict[str, Any]:
    """PB-18: estimate the retained model and every alternative; compare."""
    floor = alternative_floor(playbook)
    candidates = (
        alternatives
        if alternatives is not None
        else [("reversed_paths", reversed_alternative(config))]
    )
    if len(candidates) < floor:
        halt(
            IntegrityHalt(
                "fewer alternative models than the PB-18 floor",
                report={"declared": len(candidates), "floor": floor},
            )
        )
    retained = run_structural(
        frame,
        config,
        playbook=playbook,
        rworker=rworker,
        run_dir=run_dir,
        call_id=f"{call_id}-retained",
    )
    n = _complete_n(frame, config)
    rows: list[dict[str, Any]] = []
    flagged = False
    for alternative_id, alternative_config in candidates:
        report = run_structural(
            frame,
            alternative_config,
            playbook=playbook,
            rworker=rworker,
            run_dir=run_dir,
            call_id=f"{call_id}-{alternative_id}",
        )
        delta_chisq = report["fit"]["chisq"] - retained["fit"]["chisq"]
        delta_k = report["model"]["nfree"] - retained["model"]["nfree"]
        delta_aic = delta_chisq + 2.0 * delta_k
        delta_bic = delta_chisq + math.log(n) * delta_k
        preferred = delta_aic < 0.0 and delta_bic < 0.0
        flagged = flagged or preferred
        rows.append(
            {
                "id": alternative_id,
                "fit": report["fit"],
                "nfree": report["model"]["nfree"],
                "delta_aic": delta_aic,
                "delta_bic": delta_bic,
                "preferred": preferred,
            }
        )
    return {
        "retained": {"fit": retained["fit"], "nfree": retained["model"]["nfree"]},
        "alternatives": rows,
        "n": n,
        "flagged": flagged,
    }


def achieved_power_report(config: StudyConfig, *, n: int, playbook: Playbook) -> dict[str, Any]:
    """FR-402/PB-19: achieved close-fit power at the final analytical N."""
    floor = power_floor(playbook)
    df = model_df(config)
    value = close_fit_power(df=df, n=n)
    return {"value": value, "df": df, "n": n, "floor": floor, "flagged": value < floor}


def robustness_store_rows(
    report: Mapping[str, Any], power: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """ResultsStore.write payloads under the PB-18/19 output prefixes."""
    common = {"stage": "robustness", "engine": "py_pandas"}
    rows: list[dict[str, Any]] = []
    for alternative in report["alternatives"]:
        base = f"robustness.alternatives.{alternative['id']}"
        rows.append(
            {
                **common,
                "playbook_step": "PB-18",
                "id": f"{base}.delta_aic",
                "value": alternative["delta_aic"],
                "n": int(report["n"]),
            }
        )
        rows.append(
            {
                **common,
                "playbook_step": "PB-18",
                "id": f"{base}.delta_bic",
                "value": alternative["delta_bic"],
                "n": int(report["n"]),
            }
        )
        rows.append(
            {
                **common,
                "playbook_step": "PB-18",
                "id": f"{base}.preferred",
                "value": bool(alternative["preferred"]),
            }
        )
    rows.append(
        {
            **common,
            "playbook_step": "PB-19",
            "id": "robustness.achieved_power",
            "value": float(power["value"]),
            "df": float(power["df"]),
            "n": int(power["n"]),
        }
    )
    return rows
