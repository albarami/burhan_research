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
        if (hypothesis.to, hypothesis.from_) not in direct_pairs:
            halt(
                IntegrityHalt(
                    "indirect hypothesis requires the direct path in the model "
                    "(PB-17 decomposition)",
                    report={
                        "hypothesis": hypothesis.id,
                        "from": hypothesis.from_,
                        "to": hypothesis.to,
                    },
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


def classify_effect(direct: Mapping[str, Any], indirect: Mapping[str, Any]) -> str:
    """Zhao–Lynch–Chen typology from CI significance and sign (PB-17)."""

    def _significant(block: Mapping[str, Any]) -> bool:
        return float(block["ci_low"]) > 0.0 or float(block["ci_high"]) < 0.0

    indirect_significant = _significant(indirect)
    direct_significant = _significant(direct)
    if indirect_significant and direct_significant:
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
    rows: list[dict[str, Any]] = []
    for spec in payload["indirect"]:
        entry = by_id[spec["id"]]
        blocks = {
            name: _validate_block(entry.get(name), name=name, hypothesis=spec["id"])
            for name in _BLOCKS
        }
        rows.append(
            {
                "hypothesis": spec["id"],
                "from": spec["from"],
                "to": spec["to"],
                "via": list(spec["via"]),
                "direct": blocks["direct"],
                "indirect": blocks["indirect"],
                "total": blocks["total"],
                "classification": classify_effect(blocks["direct"], blocks["indirect"]),
            }
        )
    return {
        "bootstrap": bootstrap,
        "paths": [dict(row) for row in result.get("paths", []) if isinstance(row, Mapping)],
        "effects": rows,
        "sums": [dict(row) for row in result.get("sums", []) if isinstance(row, Mapping)],
    }


def effects_store_rows(report: Mapping[str, Any], *, created: str) -> list[dict[str, Any]]:
    """Schema-valid results-store rows under the PB-17 output prefixes."""
    ci_level = float(report["bootstrap"]["ci_level"])
    common = {
        "schema_version": 1,
        "stage": "effects",
        "engine": "r_lavaan",
        "playbook_step": "PB-17",
        "created": created,
        "hash": "0" * 64,
    }
    entries: list[dict[str, Any]] = []
    for row in report["effects"]:
        pair = f"{row['from']}->{row['to']}"
        via = "via_" + "_".join(row["via"])
        for name, family in (("direct", "direct"), ("indirect", "indirect"), ("total", "total")):
            block = row[name]
            suffix = f".{via}" if family == "indirect" else ""
            entry: dict[str, Any] = {
                **common,
                "id": f"effects.{family}.{pair}{suffix}",
                "value": block["est"],
                "se": block["se"],
                "ci_low": block["ci_low"],
                "ci_high": block["ci_high"],
                "ci_level": ci_level,
            }
            if block["p"] is not None:
                entry["p"] = block["p"]
            entries.append(entry)
        entries.append(
            {
                **common,
                "id": f"effects.classification.{pair}.{via}",
                "value": row["classification"],
            }
        )
    return entries
