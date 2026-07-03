"""Respecification controller (FR-709; PB-14).

Modification indices are consulted for WITHIN-construct error
covariances only: cross-construct suggestions and anything touching a
latent are filtered out regardless of size. Eligible suggestions apply
cumulatively, one at a time in MI order, with re-estimation after each,
until the policy cap (``measurement.respecification.max_modifications``)
or no suggestion clears the PB-14 MI floor. Each applied modification
is logged with its MI, EPC, and justification rule.

Worker-call contract: the payload is the measurement CFA payload plus
``mi: true`` and the cumulative ``error_covariances`` pair list; the
result must carry ``fit`` and an ``mi`` block of ``{lhs, rhs, mi, epc}``
rows. Every block is validated; malformed results halt typed.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeGuard

from burhan.core.errors import IntegrityHalt, halt
from burhan.stats.measurement import build_measurement_payload

if TYPE_CHECKING:
    import pandas as pd  # type: ignore[import-untyped]

    from burhan.core.artifacts.models import StudyConfig
    from burhan.core.playbook import Playbook
    from burhan.core.policy import DecisionLog, Policy
    from burhan.core.rworker import RWorker

_CAP_RULE = "measurement.respecification.max_modifications"
_FLOOR_CRITERION = "mi_floor"


def _is_number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def mi_floor(playbook: Playbook) -> float:
    """The PB-14 MI significance floor (governed value, not a constant)."""
    for criterion in playbook.criteria("PB-14"):
        if criterion.get("name") != _FLOOR_CRITERION:
            continue
        value = criterion.get("value")
        if not _is_number(value):
            break
        return float(value)
    halt(
        IntegrityHalt(
            "PB-14 does not state a numeric MI floor",
            report={"step": "PB-14", "criterion": _FLOOR_CRITERION},
        )
    )


def _modification_cap(policy: Policy) -> int:
    value = policy.rule(_CAP_RULE)
    if not _is_number(value) or int(value) != value or int(value) < 0:
        halt(
            IntegrityHalt(
                "policy respecification cap is not a non-negative integer",
                report={"rule": _CAP_RULE},
            )
        )
    return int(value)


def _validated_mi(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    block = result.get("mi")
    if not isinstance(block, list):
        halt(
            IntegrityHalt(
                "respecification worker result lacks an mi block",
                report={"block": "mi"},
            )
        )
    rows: list[dict[str, Any]] = []
    for entry in block:
        if not isinstance(entry, Mapping):
            halt(
                IntegrityHalt(
                    "respecification mi entry is not a mapping",
                    report={"block": "mi"},
                )
            )
        lhs = entry.get("lhs")
        rhs = entry.get("rhs")
        if not isinstance(lhs, str) or not isinstance(rhs, str):
            halt(
                IntegrityHalt(
                    "respecification mi entry is missing lhs/rhs",
                    report={"block": "mi"},
                )
            )
        for field in ("mi", "epc"):
            if not _is_number(entry.get(field)):
                halt(
                    IntegrityHalt(
                        f"respecification mi entry carries a nonnumeric {field}",
                        report={"lhs": lhs, "rhs": rhs, "field": field},
                    )
                )
        rows.append({"lhs": lhs, "rhs": rhs, "mi": float(entry["mi"]), "epc": float(entry["epc"])})
    return rows


def _validated_fit(result: object) -> dict[str, Any]:
    if not isinstance(result, Mapping):
        halt(
            IntegrityHalt(
                "respecification worker result is not a mapping",
                report={"block": "result"},
            )
        )
    fit = result.get("fit")
    if not isinstance(fit, Mapping) or not _is_number(fit.get("chisq")):
        halt(
            IntegrityHalt(
                "respecification worker result lacks a numeric fit block",
                report={"block": "fit"},
            )
        )
    return dict(fit)


def run_respecification(
    frame: pd.DataFrame,
    config: StudyConfig,
    *,
    policy: Policy,
    playbook: Playbook,
    log: DecisionLog,
    rworker: RWorker,
    run_dir: Any,
    call_id: str,
    approach: str | None = None,
) -> dict[str, Any]:
    """PB-14 in full: filter, order, apply one at a time, cap, log."""
    floor = mi_floor(playbook)
    cap = _modification_cap(policy)
    item_to_construct = {item.code: item.construct_ref for item in config.instrument.items}

    def _call(pairs: list[list[str]], step: str) -> dict[str, Any]:
        payload = build_measurement_payload(frame, config, approach=approach)
        payload["mi"] = True
        if pairs:
            payload["error_covariances"] = [list(pair) for pair in pairs]
        result = rworker.call(
            "measurement_worker", payload, call_id=f"{call_id}-{step}", run_dir=run_dir, seed=1
        )
        _validated_fit(result)
        return dict(result)

    current = _call([], "base")
    baseline_fit = _validated_fit(current)
    applied: list[list[str]] = []
    modifications: list[dict[str, Any]] = []
    filtered: list[dict[str, Any]] = []
    filtered_seen: set[tuple[str, str, str]] = set()
    stopped = "no_eligible_suggestion"

    def _filter(row: dict[str, Any], reason: str) -> None:
        key = (row["lhs"], row["rhs"], reason)
        if key not in filtered_seen:
            filtered_seen.add(key)
            filtered.append({**row, "reason": reason})

    while True:
        eligible: list[dict[str, Any]] = []
        for row in sorted(_validated_mi(current), key=lambda r: (-r["mi"], r["lhs"], r["rhs"])):
            constructs = (item_to_construct.get(row["lhs"]), item_to_construct.get(row["rhs"]))
            if constructs[0] is None or constructs[0] != constructs[1]:
                _filter(row, "not_within_construct")
            elif row["mi"] < floor:
                _filter(row, "below_mi_floor")
            elif sorted((row["lhs"], row["rhs"])) not in [sorted(p) for p in applied]:
                eligible.append(row)
        if not eligible:
            stopped = "no_eligible_suggestion"
            break
        if len(modifications) >= cap:
            stopped = "policy_cap"
            break
        top = eligible[0]
        pair = [top["lhs"], top["rhs"]]
        applied.append(pair)
        current = _call(applied, f"m{len(applied)}")
        modifications.append(
            {
                "pair": pair,
                "mi": top["mi"],
                "epc": top["epc"],
                "fit_after": _validated_fit(current),
            }
        )
        log.append(
            {
                "stage": "measurement",
                "decision_point": "respecification",
                "rule_id": _CAP_RULE,
                "rule_version": policy.version,
                "inputs": {"pair": pair, "mi": top["mi"], "epc": top["epc"]},
                "decision": f"error covariance {pair[0]}~~{pair[1]} applied",
                "rationale": (
                    "PB-14: within-construct, above the MI floor, applied "
                    "cumulatively one at a time under the policy cap (FR-709)."
                ),
            }
        )
    return {
        "baseline_fit": baseline_fit,
        "final_fit": _validated_fit(current),
        "modifications": modifications,
        "filtered": filtered,
        "stopped": stopped,
    }
