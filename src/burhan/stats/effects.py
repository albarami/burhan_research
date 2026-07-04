"""Bootstrapped effects decomposition and ZLC classification (FR-802; PB-17).

Direct, indirect, and total effects for every hypothesized indirect
path, estimated with bias-corrected bootstrap CIs whose resample count,
level, and type come from the policy layer — never constants. The
Zhao–Lynch–Chen typology (complementary, competitive, indirect-only,
direct-only, no-effect) is applied engine-side from the validated CI
blocks, so every hypothesized indirect effect receives a classification
entry. Statistic-store rows carry the grammar-conformant IDs the
hypothesis matrix references (FR-1103 backbone).

Every worker result block is validated with typed halts: finiteness,
scientific ranges, CI order, the bootstrap echo (requested = returned =
completed), and exact hypothesis-id coverage.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeGuard

from burhan.core.errors import IntegrityHalt, halt
from burhan.stats.measurement import build_measurement_payload

if TYPE_CHECKING:
    import pandas as pd  # type: ignore[import-untyped]

    from burhan.core.artifacts.models import StudyConfig
    from burhan.core.playbook import Playbook
    from burhan.core.policy import Policy
    from burhan.core.rworker import RWorker

_RESAMPLES_RULE = "effects.bootstrap.resamples"
_CI_LEVEL_RULE = "effects.bootstrap.ci_level"
_CI_TYPE_RULE = "effects.bootstrap.ci_type"
_CI_TYPES = ("bias_corrected", "percentile")
_BLOCKS = ("direct", "indirect", "total")


def _is_number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_finite(value: object) -> TypeGuard[int | float]:
    return _is_number(value) and math.isfinite(value)


def bootstrap_settings(policy: Policy) -> dict[str, Any]:
    """PB-17 bootstrap parameters from the policy layer, validated typed."""
    resamples = policy.rule(_RESAMPLES_RULE)
    if not _is_finite(resamples) or int(resamples) != resamples or int(resamples) <= 0:
        halt(
            IntegrityHalt(
                "policy bootstrap resamples is not a positive integer",
                report={"rule": _RESAMPLES_RULE},
            )
        )
    ci_level = policy.rule(_CI_LEVEL_RULE)
    if not _is_finite(ci_level) or not 0.0 < ci_level < 1.0:
        halt(
            IntegrityHalt(
                "policy bootstrap ci_level is not in (0, 1)",
                report={"rule": _CI_LEVEL_RULE},
            )
        )
    ci_type = policy.rule(_CI_TYPE_RULE)
    if ci_type not in _CI_TYPES:
        halt(
            IntegrityHalt(
                "policy bootstrap ci_type is not a recognized interval type",
                report={"rule": _CI_TYPE_RULE, "allowed": list(_CI_TYPES)},
            )
        )
    return {"resamples": int(resamples), "ci_level": float(ci_level), "ci_type": str(ci_type)}


def build_effects_payload(
    frame: pd.DataFrame, config: StudyConfig, *, policy: Policy
) -> dict[str, Any]:
    """The worker payload: chain-complete regressions + indirect specs."""
    known = {construct.code for construct in config.constructs}
    direct_pairs: list[tuple[str, str]] = []
    for hypothesis in config.hypotheses:
        if hypothesis.effect == "direct":
            direct_pairs.append((hypothesis.to, hypothesis.from_))
    specs: list[dict[str, Any]] = []
    chain_pairs: list[tuple[str, str]] = []
    for hypothesis in config.hypotheses:
        if hypothesis.effect != "indirect":
            continue
        via = list(hypothesis.via or [])
        if not via:
            halt(
                IntegrityHalt(
                    "indirect hypothesis declares no via chain",
                    report={"hypothesis": hypothesis.id},
                )
            )
        codes = [hypothesis.from_, *via, hypothesis.to]
        unknown = [code for code in codes if code not in known]
        if unknown:
            halt(
                IntegrityHalt(
                    "indirect hypothesis references an unknown construct",
                    report={"hypothesis": hypothesis.id, "unknown": unknown},
                )
            )
        for index in range(len(codes) - 1):
            chain_pairs.append((codes[index + 1], codes[index]))
        specs.append(
            {"id": hypothesis.id, "from": hypothesis.from_, "to": hypothesis.to, "via": via}
        )
    if not specs:
        halt(
            IntegrityHalt(
                "the contract declares no hypothesized indirect effect",
                report={"hypotheses": len(config.hypotheses)},
            )
        )
    regressions: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for lhs, rhs in [*direct_pairs, *chain_pairs]:
        if (lhs, rhs) not in seen:
            seen.add((lhs, rhs))
            regressions.append({"lhs": lhs, "rhs": rhs})
    approach = str(config.higher_order.approach) if config.higher_order is not None else None
    payload = build_measurement_payload(frame, config, approach=approach)
    payload["op"] = "effects"
    payload["carrier"] = (
        str(config.higher_order.structural_carry) if config.higher_order is not None else None
    )
    payload["regressions"] = regressions
    payload["indirect"] = specs
    payload["bootstrap"] = bootstrap_settings(policy)
    return payload


def _validate_block(block: object, *, name: str, hypothesis: str) -> dict[str, Any]:
    if not isinstance(block, Mapping):
        halt(
            IntegrityHalt(
                f"effects {name} block is missing or malformed",
                report={"hypothesis": hypothesis, "block": name},
            )
        )
    est = block.get("est")
    if not _is_finite(est):
        halt(
            IntegrityHalt(
                f"effects {name} block carries an invalid est",
                report={"hypothesis": hypothesis, "field": "est"},
            )
        )
    se = block.get("se")
    if not _is_finite(se) or se < 0.0:
        halt(
            IntegrityHalt(
                f"effects {name} block carries an invalid se",
                report={"hypothesis": hypothesis, "field": "se"},
            )
        )
    for bound in ("ci_low", "ci_high"):
        if not _is_finite(block.get(bound)):
            halt(
                IntegrityHalt(
                    f"effects {name} block carries an invalid {bound}",
                    report={"hypothesis": hypothesis, "field": bound},
                )
            )
    if float(block["ci_low"]) > float(block["ci_high"]):
        halt(
            IntegrityHalt(
                f"effects {name} block ci bounds are out of order",
                report={"hypothesis": hypothesis, "block": name},
            )
        )
    p_value = block.get("p")
    if p_value is not None and (not _is_finite(p_value) or not 0.0 <= p_value <= 1.0):
        halt(
            IntegrityHalt(
                f"effects {name} block carries an invalid p",
                report={"hypothesis": hypothesis, "field": "p"},
            )
        )
    return {
        "est": float(est),
        "se": float(se),
        "ci_low": float(block["ci_low"]),
        "ci_high": float(block["ci_high"]),
        "p": None if p_value is None else float(p_value),
    }


def classify_effect(direct: Mapping[str, Any] | None, indirect: Mapping[str, Any]) -> str:
    """Zhao–Lynch–Chen typology from CI significance and sign (PB-17).

    A model that declares no direct edge constrains the direct effect to
    zero: it is definitionally not significant, which lands in Zhao's
    indirect-only / no-effect branch (zhao2010).
    """

    def _significant(block: Mapping[str, Any]) -> bool:
        return float(block["ci_low"]) > 0.0 or float(block["ci_high"]) < 0.0

    indirect_significant = _significant(indirect)
    direct_significant = direct is not None and _significant(direct)
    if indirect_significant and direct_significant and direct is not None:
        if float(direct["est"]) * float(indirect["est"]) > 0.0:
            return "complementary"
        return "competitive"
    if indirect_significant:
        return "indirect_only"
    if direct_significant:
        return "direct_only"
    return "no_effect"


def _validate_bootstrap_echo(block: object, *, requested: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(block, Mapping):
        halt(
            IntegrityHalt(
                "effects worker result lacks a bootstrap block",
                report={"block": "bootstrap"},
            )
        )
    if block.get("resamples") != requested["resamples"]:
        halt(
            IntegrityHalt(
                "effects worker resamples echo differs from the policy request",
                report={
                    "requested": requested["resamples"],
                    "returned": repr(block.get("resamples")),
                },
            )
        )
    completed = block.get("completed")
    if not _is_finite(completed) or int(completed) != completed:
        halt(
            IntegrityHalt(
                "effects bootstrap completed count is malformed",
                report={"field": "completed"},
            )
        )
    if int(completed) != requested["resamples"]:
        halt(
            IntegrityHalt(
                "effects bootstrap completed fewer draws than requested",
                report={"requested": requested["resamples"], "completed": int(completed)},
            )
        )
    if (
        block.get("ci_level") != requested["ci_level"]
        or block.get("ci_type") != requested["ci_type"]
    ):
        halt(
            IntegrityHalt(
                "effects worker ci settings echo differs from the policy request",
                report={"requested": dict(requested)},
            )
        )
    return {
        "resamples": requested["resamples"],
        "completed": int(completed),
        "ci_level": requested["ci_level"],
        "ci_type": requested["ci_type"],
    }


def run_effects(
    frame: pd.DataFrame,
    config: StudyConfig,
    *,
    policy: Policy,
    playbook: Playbook,
    rworker: RWorker,
    run_dir: Any,
    call_id: str,
) -> dict[str, Any]:
    """PB-17 in full: bootstrap decomposition + classification per hypothesis."""
    criteria = {str(c.get("name")) for c in playbook.criteria("PB-17")}
    if "classification" not in criteria or "resamples" not in criteria:
        halt(
            IntegrityHalt(
                "PB-17 does not declare the resamples and classification criteria",
                report={"step": "PB-17"},
            )
        )
    payload = build_effects_payload(frame, config, policy=policy)
    result = rworker.call("effects_worker", payload, call_id=call_id, run_dir=run_dir, seed=1)
    if not isinstance(result, Mapping):
        halt(
            IntegrityHalt(
                "effects worker result is not a mapping",
                report={"block": "result"},
            )
        )
    bootstrap = _validate_bootstrap_echo(result.get("bootstrap"), requested=payload["bootstrap"])
    entries = result.get("effects")
    if not isinstance(entries, list):
        halt(
            IntegrityHalt(
                "effects worker result lacks an effects block",
                report={"block": "effects"},
            )
        )
    by_id: dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("id"), str):
            halt(
                IntegrityHalt(
                    "effects entry is malformed",
                    report={"block": "effects"},
                )
            )
        entry_id = str(entry["id"])
        if entry_id in by_id:
            halt(
                IntegrityHalt(
                    "effects worker returned a duplicate hypothesis id",
                    report={"duplicate": entry_id},
                )
            )
        by_id[entry_id] = entry
    expected = [spec["id"] for spec in payload["indirect"]]
    missing = sorted(set(expected) - set(by_id))
    if missing:
        halt(
            IntegrityHalt(
                "effects worker result is missing hypothesized effect ids",
                report={"missing": missing},
            )
        )
    extra = sorted(set(by_id) - set(expected))
    if extra:
        halt(
            IntegrityHalt(
                "effects worker returned extra hypothesis ids",
                report={"extra": extra},
            )
        )
    edge_pairs = {
        (str(regression["lhs"]), str(regression["rhs"])) for regression in payload["regressions"]
    }
    rows: list[dict[str, Any]] = []
    for spec in payload["indirect"]:
        entry = by_id[spec["id"]]
        has_direct = (spec["to"], spec["from"]) in edge_pairs
        indirect_block = _validate_block(
            entry.get("indirect"), name="indirect", hypothesis=spec["id"]
        )
        if has_direct:
            direct_block: dict[str, Any] | None = _validate_block(
                entry.get("direct"), name="direct", hypothesis=spec["id"]
            )
            total_block: dict[str, Any] | None = _validate_block(
                entry.get("total"), name="total", hypothesis=spec["id"]
            )
        else:
            for name in ("direct", "total"):
                if entry.get(name) is not None:
                    halt(
                        IntegrityHalt(
                            f"effects worker returned a {name} block for an undeclared direct edge",
                            report={"hypothesis": spec["id"], "block": name},
                        )
                    )
            direct_block = None
            total_block = None
        rows.append(
            {
                "hypothesis": spec["id"],
                "from": spec["from"],
                "to": spec["to"],
                "via": list(spec["via"]),
                "direct": direct_block,
                "indirect": indirect_block,
                "total": total_block,
                "classification": classify_effect(direct_block, indirect_block),
            }
        )
    expected_pairs = [
        (str(regression["lhs"]), str(regression["rhs"])) for regression in payload["regressions"]
    ]
    group_counts: dict[tuple[str, str], int] = {}
    for spec in payload["indirect"]:
        key = (str(spec["from"]), str(spec["to"]))
        group_counts[key] = group_counts.get(key, 0) + 1
    expected_sums = sorted(key for key, count in group_counts.items() if count > 1)
    return {
        "bootstrap": bootstrap,
        "paths": _validate_paths(result.get("paths"), expected=expected_pairs),
        "effects": rows,
        "sums": _validate_sums(result.get("sums"), expected=expected_sums),
    }


def _validate_paths(block: object, *, expected: list[tuple[str, str]]) -> list[dict[str, Any]]:
    if not isinstance(block, list):
        halt(
            IntegrityHalt(
                "effects worker paths block is not a list",
                report={"block": "paths"},
            )
        )
    validated: list[dict[str, Any]] = []
    returned: list[tuple[str, str]] = []
    for entry in block:
        if not isinstance(entry, Mapping) or not all(
            isinstance(entry.get(key), str) for key in ("lhs", "rhs")
        ):
            halt(
                IntegrityHalt(
                    "effects paths entry is malformed",
                    report={"block": "paths"},
                )
            )
        pair = (str(entry["lhs"]), str(entry["rhs"]))
        if pair in returned:
            halt(
                IntegrityHalt(
                    "effects paths carry duplicate pairs",
                    report={"duplicate": list(pair)},
                )
            )
        returned.append(pair)
        validated.append(
            _validate_block(entry, name="paths", hypothesis=f"{pair[0]}~{pair[1]}")
            | {"lhs": pair[0], "rhs": pair[1]}
        )
    missing = sorted(set(expected) - set(returned))
    if missing:
        halt(
            IntegrityHalt(
                "effects paths are missing model pairs",
                report={"missing": [list(pair) for pair in missing]},
            )
        )
    extra = sorted(set(returned) - set(expected))
    if extra:
        halt(
            IntegrityHalt(
                "effects paths carry extra unrequested pairs",
                report={"extra": [list(pair) for pair in extra]},
            )
        )
    return validated


def _validate_sums(block: object, *, expected: list[tuple[str, str]]) -> list[dict[str, Any]]:
    if not isinstance(block, list):
        halt(
            IntegrityHalt(
                "effects worker sums block is not a list",
                report={"block": "sums"},
            )
        )
    validated: list[dict[str, Any]] = []
    returned: list[tuple[str, str]] = []
    for entry in block:
        if not isinstance(entry, Mapping) or not all(
            isinstance(entry.get(key), str) for key in ("from", "to")
        ):
            halt(
                IntegrityHalt(
                    "effects sums entry is malformed",
                    report={"block": "sums"},
                )
            )
        pair = (str(entry["from"]), str(entry["to"]))
        if pair in returned:
            halt(
                IntegrityHalt(
                    "effects sums carry duplicate groups",
                    report={"duplicate": list(pair)},
                )
            )
        returned.append(pair)
        validated.append(
            _validate_block(entry, name="sums", hypothesis=f"{pair[0]}->{pair[1]}")
            | {"from": pair[0], "to": pair[1]}
        )
    missing = sorted(set(expected) - set(returned))
    if missing:
        halt(
            IntegrityHalt(
                "effects sums are missing indirect groups",
                report={"missing": [list(pair) for pair in missing]},
            )
        )
    extra = sorted(set(returned) - set(expected))
    if extra:
        halt(
            IntegrityHalt(
                "effects sums carry extra unrequested groups",
                report={"extra": [list(pair) for pair in extra]},
            )
        )
    return validated


def effects_store_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    """ResultsStore.write payloads under the PB-17 output prefixes.

    The store owns ``schema_version``, ``created``, and ``hash`` — these
    payloads carry none of them, so every row is writable through the
    append-only store as-is. Direct/total entries are emitted only when
    the model declares the direct edge.
    """
    ci_level = float(report["bootstrap"]["ci_level"])
    common = {
        "stage": "effects",
        "engine": "r_lavaan",
        "playbook_step": "PB-17",
    }

    def _numeric_entry(stat_id: str, block: Mapping[str, Any]) -> dict[str, Any]:
        entry: dict[str, Any] = {
            **common,
            "id": stat_id,
            "value": block["est"],
            "se": block["se"],
            "ci_low": block["ci_low"],
            "ci_high": block["ci_high"],
            "ci_level": ci_level,
        }
        if block["p"] is not None:
            entry["p"] = block["p"]
        return entry

    entries: list[dict[str, Any]] = []
    # every declared edge is a bootstrap-estimated direct effect
    for path in report["paths"]:
        entries.append(_numeric_entry(f"effects.direct.{path['rhs']}->{path['lhs']}", path))
    for row in report["effects"]:
        pair = f"{row['from']}->{row['to']}"
        via = "via_" + "_".join(row["via"])
        entries.append(_numeric_entry(f"effects.indirect.{pair}.{via}", row["indirect"]))
        if row["total"] is not None:
            entries.append(_numeric_entry(f"effects.total.{pair}", row["total"]))
        entries.append(
            {
                **common,
                "id": f"effects.classification.{pair}.{via}",
                "value": row["classification"],
            }
        )
    return entries
