"""Certified parity map + tolerance checks (FR-902/903).

The benchmark replication runner writes the certified parity map;
verification consumes it. Every compared scope must be certified with
its own tolerance; scopes declared non-parity are flagged and never
compared; a scope the map does not mention at all is a configuration
defect and halts typed. Deltas beyond the tolerance flag with the
scope named; beyond the policy halt multiplier the run halts with
``HALTED_VERIFICATION`` and a per-estimate diff.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, TypeGuard

from burhan.core.errors import IntegrityHalt, VerificationHalt, halt

if TYPE_CHECKING:
    from burhan.core.policy import Policy


def _is_finite(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def verification_settings(policy: Policy) -> dict[str, float]:
    """FR-902 tolerances from the policy layer, validated typed."""
    prep = policy.rule("verification.prep_cell_tolerance")
    if not _is_finite(prep) or prep < 0.0:
        halt(
            IntegrityHalt(
                "policy prep_cell_tolerance is not a non-negative number",
                report={"rule": "verification.prep_cell_tolerance"},
            )
        )
    estimate = policy.rule("verification.estimate_abs_tolerance")
    if not _is_finite(estimate) or estimate <= 0.0:
        halt(
            IntegrityHalt(
                "policy estimate_abs_tolerance is not a positive number",
                report={"rule": "verification.estimate_abs_tolerance"},
            )
        )
    multiplier = policy.rule("verification.halt_multiplier")
    if not _is_finite(multiplier) or multiplier <= 1.0:
        halt(
            IntegrityHalt(
                "policy halt_multiplier must be a number greater than 1",
                report={"rule": "verification.halt_multiplier"},
            )
        )
    return {
        "prep_cell_tolerance": float(prep),
        "estimate_abs_tolerance": float(estimate),
        "halt_multiplier": float(multiplier),
    }


def load_parity_map(data: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the certified parity map shape (written by the runner)."""
    certified = data.get("certified")
    if not isinstance(certified, Mapping) or not certified:
        halt(
            IntegrityHalt(
                "parity map lacks a certified scopes block",
                report={"block": "certified"},
            )
        )
    scopes: dict[str, dict[str, float]] = {}
    for scope, spec in certified.items():
        tolerance = spec.get("tolerance") if isinstance(spec, Mapping) else None
        if not _is_finite(tolerance) or tolerance <= 0.0:
            halt(
                IntegrityHalt(
                    "parity map scope tolerance is not a positive number",
                    report={"scope": str(scope)},
                )
            )
        scopes[str(scope)] = {"tolerance": float(tolerance)}
    non_parity = data.get("non_parity", [])
    if not isinstance(non_parity, Sequence) or isinstance(non_parity, str):
        halt(
            IntegrityHalt(
                "parity map non_parity block is not a list",
                report={"block": "non_parity"},
            )
        )
    return {"certified": scopes, "non_parity": [str(scope) for scope in non_parity]}


def parity_check(
    pairs: Sequence[Mapping[str, Any]],
    *,
    parity_map: Mapping[str, Any],
    settings: Mapping[str, Any],
) -> dict[str, Any]:
    """FR-902/903 semantics over (engine, independent) estimate pairs."""
    certified: Mapping[str, Mapping[str, float]] = parity_map["certified"]
    non_parity = set(parity_map["non_parity"])
    multiplier = float(settings["halt_multiplier"])
    results: list[dict[str, Any]] = []
    flags: list[str] = []
    declared_scopes: set[str] = set()
    halt_diffs: list[dict[str, Any]] = []
    for entry in pairs:
        scope = str(entry["scope"])
        stat_id = str(entry["id"])
        if scope in non_parity:
            if scope not in declared_scopes:
                declared_scopes.add(scope)
                flags.append(
                    f"out-of-parity scope '{scope}' declared in FLAGS; not compared (FR-903)"
                )
            results.append({"scope": scope, "id": stat_id, "status": "declared_out_of_parity"})
            continue
        if scope not in certified:
            halt(
                IntegrityHalt(
                    "scope is not covered by the certified parity map",
                    report={"scope": scope, "id": stat_id},
                )
            )
        for side in ("engine_value", "independent_value"):
            if not _is_finite(entry.get(side)):
                halt(
                    IntegrityHalt(
                        f"parity pair carries a nonfinite {side}",
                        report={"scope": scope, "id": stat_id, "field": side},
                    )
                )
        tolerance = certified[scope]["tolerance"]
        delta = abs(float(entry["engine_value"]) - float(entry["independent_value"]))
        record = {
            "scope": scope,
            "id": stat_id,
            "delta": delta,
            "tolerance": tolerance,
        }
        if delta <= tolerance:
            results.append({**record, "status": "pass"})
        elif delta <= multiplier * tolerance:
            results.append({**record, "status": "flagged"})
            flags.append(
                f"scope '{scope}' estimate {stat_id} beyond tolerance "
                f"(delta {delta:.6f} > {tolerance}) but below the halt multiplier"
            )
        else:
            results.append({**record, "status": "halt"})
            halt_diffs.append(
                {
                    "scope": scope,
                    "id": stat_id,
                    "engine_value": float(entry["engine_value"]),
                    "independent_value": float(entry["independent_value"]),
                    "delta": delta,
                    "tolerance": tolerance,
                }
            )
    if halt_diffs:
        halt(
            VerificationHalt(
                "independent verification diverged beyond the halt multiplier",
                report={"diffs": halt_diffs, "halt_multiplier": multiplier},
            )
        )
    return {"results": results, "flags": flags}
