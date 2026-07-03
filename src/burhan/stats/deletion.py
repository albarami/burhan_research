"""Item-deletion protocol behind the PD-05 permit (FR-705–708; PB-13).

Protected by default: candidates surface as a :class:`Recommendation`
and nothing executes. Under a :class:`PermitToken` the protocol deletes
one item per step with full re-estimation between steps — the single
model-shrinking primitive removes exactly one item; no code path
removes more than one at once (AT-M10-5). Every step enforces the dual trigger (statistical
signal AND content-validity attestation), the three-item floor, and the
designed-with-fewer-than-three deletion-lock; each executed deletion
carries a complete before/after audit and flags validated-instrument
deviations. Thresholds come from the governed playbook, never from
constants here.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeGuard

from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig
from burhan.core.errors import IntegrityHalt, halt
from burhan.core.registry import PermitToken, Recommendation
from burhan.stats.measurement import run_measurement

if TYPE_CHECKING:
    import pandas as pd  # type: ignore[import-untyped]

    from burhan.core.playbook import Playbook
    from burhan.core.policy import DecisionLog, Policy
    from burhan.core.registry import Registry
    from burhan.core.rworker import RWorker

_CANDIDATE_RULE = re.compile(r"<\s*(\d\.\d+)\s+is a deletion-candidate")
_DELETION_SIGNAL = "loading_below_playbook_target"
_FLOOR_CRITERION = "three_item_floor"


def _is_number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _valid_attestation(value: object) -> TypeGuard[str]:
    """FR-707: content-validity evidence is a non-blank string, nothing less."""
    return isinstance(value, str) and value.strip() != ""


def deletion_signal_bound(playbook: Playbook) -> float:
    """The PB-09 deletion-candidate loading bound, parsed from rule text."""
    for criterion in playbook.criteria("PB-09"):
        if criterion.get("name") != "loading_target":
            continue
        match = _CANDIDATE_RULE.search(str(criterion.get("rule", "")))
        if match is None:
            break
        return float(match.group(1))
    halt(
        IntegrityHalt(
            "PB-09 loading_target rule does not state the deletion-candidate bound",
            report={"step": "PB-09"},
        )
    )


def deletion_floor(playbook: Playbook) -> int:
    """The PB-13 three-item floor (governed value, not a constant)."""
    for criterion in playbook.criteria("PB-13"):
        if criterion.get("name") != _FLOOR_CRITERION:
            continue
        value = criterion.get("value")
        if not _is_number(value) or int(value) != value:
            break
        return int(value)
    halt(
        IntegrityHalt(
            "PB-13 does not state an integer three-item floor",
            report={"step": "PB-13", "criterion": _FLOOR_CRITERION},
        )
    )


def deletion_candidates(report: Mapping[str, Any], *, playbook: Playbook) -> list[dict[str, Any]]:
    """Statistical deletion signals from a measurement report, worst first."""
    bound = deletion_signal_bound(playbook)
    candidates: list[dict[str, Any]] = []
    first = report.get("first_order")
    loadings = first.get("loadings", []) if isinstance(first, Mapping) else []
    for entry in loadings:
        std = entry.get("std")
        if not _is_number(std):
            halt(
                IntegrityHalt(
                    "measurement loading carries a nonnumeric std in candidate scan",
                    report={
                        "construct": str(entry.get("construct")),
                        "item": str(entry.get("item")),
                    },
                )
            )
        if std < bound:
            candidates.append(
                {
                    "construct": str(entry["construct"]),
                    "item": str(entry["item"]),
                    "std": float(std),
                    "signal": _DELETION_SIGNAL,
                }
            )
    candidates.sort(key=lambda c: (c["std"], c["construct"], c["item"]))
    return candidates


def _without_item(config: StudyConfig, *, item: str) -> StudyConfig:
    """The analysis model minus exactly one item (the design stays intact)."""
    data = config.model_dump(mode="python", exclude_none=True, by_alias=True)
    data["instrument"]["items"] = [
        record for record in data["instrument"]["items"] if record["code"] != item
    ]
    for construct in data["constructs"]:
        indicators = construct.get("indicators")
        if indicators is not None:
            construct["indicators"] = [code for code in indicators if code != item]
    return validate_and_build(StudyConfig, data)


def _audit_view(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "reliability": report["first_order"]["reliability"],
        "validity": report["validity"],
        "fit": report["fit"],
    }


def _validated_deviation(config: StudyConfig, *, construct: str, item: str) -> bool:
    for record in config.constructs:
        if record.code == construct and record.source is not None:
            return True
    for entry in config.instrument.items:
        if entry.code == item and entry.source is not None:
            return True
    return False


def run_deletion_protocol(
    frame: pd.DataFrame,
    config: StudyConfig,
    *,
    policy: Policy,
    playbook: Playbook,
    registry: Registry,
    log: DecisionLog,
    rworker: RWorker,
    run_dir: Any,
    call_id: str,
    content_validity: Mapping[str, object],
    approach: str | None = None,
) -> dict[str, Any]:
    """PB-13 in full: recommend under protection, execute under permit."""
    report = run_measurement(
        frame,
        config,
        policy=policy,
        playbook=playbook,
        rworker=rworker,
        run_dir=run_dir,
        call_id=f"{call_id}-base",
        approach=approach,
    )
    candidates = deletion_candidates(report, playbook=playbook)
    verdict = registry.guard(
        "PD-05",
        policy=policy,
        log=log,
        stage="measurement",
        evidence={"candidates": [dict(candidate) for candidate in candidates]},
    )
    if isinstance(verdict, Recommendation):
        return {
            "mode": "recommendation",
            "recommendation": verdict,
            "candidates": candidates,
            "deletions": [],
            "skipped": [],
            "report": report,
        }
    return _execute_under_permit(
        frame,
        config,
        token=verdict,
        baseline_report=report,
        baseline_candidates=candidates,
        policy=policy,
        playbook=playbook,
        log=log,
        rworker=rworker,
        run_dir=run_dir,
        call_id=call_id,
        content_validity=content_validity,
        approach=approach,
    )


def _execute_under_permit(
    frame: pd.DataFrame,
    config: StudyConfig,
    *,
    token: PermitToken,
    baseline_report: dict[str, Any],
    baseline_candidates: list[dict[str, Any]],
    policy: Policy,
    playbook: Playbook,
    log: DecisionLog,
    rworker: RWorker,
    run_dir: Any,
    call_id: str,
    content_validity: Mapping[str, object],
    approach: str | None,
) -> dict[str, Any]:
    floor = deletion_floor(playbook)
    designed = {
        construct.code: len(construct.indicators or [])
        for construct in config.constructs
        if construct.level == "first_order"
    }
    working = config
    report = baseline_report
    deletions: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    skip_seen: set[tuple[str, str]] = set()

    def _skip(candidate: dict[str, Any], reason: str) -> None:
        key = (candidate["item"], reason)
        if key not in skip_seen:
            skip_seen.add(key)
            skipped.append({"item": candidate["item"], "reason": reason})

    while True:
        chosen: dict[str, Any] | None = None
        current_counts = {
            construct.code: len(construct.indicators or [])
            for construct in working.constructs
            if construct.level == "first_order"
        }
        for candidate in deletion_candidates(report, playbook=playbook):
            construct = candidate["construct"]
            item = candidate["item"]
            # FR-705: only explicitly listed signals are authorized — an
            # empty granted-rules tuple authorizes nothing, not everything.
            if candidate["signal"] not in token.granted_rules:
                _skip(candidate, "signal_not_granted")
            elif designed.get(construct, 0) < floor:
                _skip(candidate, "deletion_locked")
            elif current_counts.get(construct, 0) - 1 < floor:
                _skip(candidate, "three_item_floor")
            elif item not in content_validity:
                _skip(candidate, "content_validity_missing")
            elif not _valid_attestation(content_validity[item]):
                _skip(candidate, "content_validity_invalid")
            else:
                chosen = candidate
                break
        if chosen is None:
            break
        working = _without_item(working, item=chosen["item"])
        new_report = run_measurement(
            frame,
            working,
            policy=policy,
            playbook=playbook,
            rworker=rworker,
            run_dir=run_dir,
            call_id=f"{call_id}-d{len(deletions) + 1}",
            approach=approach,
        )
        deletions.append(
            {
                "item": chosen["item"],
                "construct": chosen["construct"],
                "std": chosen["std"],
                "signal": chosen["signal"],
                "content_validity": str(content_validity[chosen["item"]]),
                "validated_instrument_deviation": _validated_deviation(
                    config, construct=chosen["construct"], item=chosen["item"]
                ),
                "before": _audit_view(report),
                "after": _audit_view(new_report),
            }
        )
        log.append(
            {
                "stage": "measurement",
                "decision_point": "item_deletion_executed",
                "rule_id": token.delegation_ref,
                "rule_version": token.policy_version,
                "inputs": {
                    "item": chosen["item"],
                    "construct": chosen["construct"],
                    "std": chosen["std"],
                    "signal": chosen["signal"],
                    "content_validity": str(content_validity[chosen["item"]]),
                },
                "decision": f"item {chosen['item']} deleted",
                "rationale": (
                    "PB-13 under PD-05 permit: dual trigger satisfied, floor "
                    "respected, one-at-a-time with full re-estimation (FR-706/707)."
                ),
            }
        )
        report = new_report
    return {
        "mode": "executed",
        "token": token,
        "candidates": baseline_candidates,
        "deletions": deletions,
        "skipped": skipped,
        "report": report,
    }
