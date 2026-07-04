"""The hypothesis testing matrix (PB-16; FR-1103 backbone).

One row per contract hypothesis: H# → path → statistic ID → verdict.
Rows are assembled exclusively from statistic IDs — no raw numbers —
so the narrate checker (TC-13) resolves every figure through the
results store. Verdicts follow the PB-16 significance rule: support
requires the governed alpha (or a CI excluding zero when no p exists),
a sign consistent with the hypothesis, and marginal p (alpha to the
parsed marginal bound) is reported as not supported.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, NoReturn, TypeGuard

from burhan.core.errors import IntegrityHalt, halt

if TYPE_CHECKING:
    from burhan.core.artifacts.models import StudyConfig
    from burhan.core.playbook import Playbook

_MARGINAL_RULE = re.compile(r"\(\s*\.(\d+)\s*[–-]\s*\.(\d+)\s*\)")
_RULE_ID = "PB-16.significance_rule"


def _is_finite(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def significance_rule(playbook: Playbook) -> dict[str, Any]:
    """PB-16 alpha and the marginal band, parsed from the governed step."""
    for criterion in playbook.criteria("PB-16"):
        if criterion.get("name") != "significance_rule":
            continue
        alpha = criterion.get("value")
        if not _is_finite(alpha) or not 0.0 < alpha < 1.0:
            break
        match = _MARGINAL_RULE.search(str(criterion.get("rule", "")))
        if match is None:
            break
        marginal_upper = float(f"0.{match.group(2)}")
        return {"alpha": float(alpha), "marginal_upper": marginal_upper, "rule_id": _RULE_ID}
    halt(
        IntegrityHalt(
            "PB-16 does not state a parseable significance rule with marginal band",
            report={"step": "PB-16", "criterion": "significance_rule"},
        )
    )


def _verdict(block: Mapping[str, Any], *, sign: str, rule: Mapping[str, Any]) -> str:
    est = float(block["est"])
    sign_ok = est > 0.0 if sign == "positive" else est < 0.0
    p_value = block.get("p")
    # PB-16: marginal p overrides the disjunction — reported as not
    # supported even when the CI excludes zero.
    if p_value is not None and rule["alpha"] <= float(p_value) < rule["marginal_upper"]:
        return "not_supported"
    ci_excludes_zero = float(block["ci_low"]) > 0.0 or float(block["ci_high"]) < 0.0
    significant = (p_value is not None and float(p_value) < rule["alpha"]) or ci_excludes_zero
    return "supported" if significant and sign_ok else "not_supported"


def build_hypothesis_matrix(
    config: StudyConfig,
    effects_report: Mapping[str, Any],
    *,
    playbook: Playbook,
) -> list[dict[str, str]]:
    """H# → path → statistic ID → verdict, from validated effects output."""
    rule = significance_rule(playbook)
    # Direct effects come from the validated bootstrap path rows (every
    # declared edge is estimated); indirect/total from the effect rows.
    direct_blocks: dict[tuple[str, str], Mapping[str, Any]] = {
        (str(row["rhs"]), str(row["lhs"])): row for row in effects_report["paths"]
    }
    indirect_rows: dict[tuple[str, str, tuple[str, ...]], Mapping[str, Any]] = {}
    total_blocks: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in effects_report["effects"]:
        pair = (str(row["from"]), str(row["to"]))
        if row["total"] is not None:
            total_blocks[pair] = row["total"]
        indirect_rows[(pair[0], pair[1], tuple(row["via"]))] = row

    def _missing(hypothesis_id: str) -> NoReturn:
        halt(
            IntegrityHalt(
                "hypothesis has no computed statistic in the effects report",
                report={"hypothesis": hypothesis_id},
            )
        )

    rows: list[dict[str, str]] = []
    for hypothesis in config.hypotheses:
        pair = (hypothesis.from_, hypothesis.to)
        pair_id = f"{hypothesis.from_}->{hypothesis.to}"
        if hypothesis.effect == "direct":
            block = direct_blocks.get(pair)
            if block is None:
                _missing(hypothesis.id)
            rows.append(
                {
                    "hypothesis": hypothesis.id,
                    "effect": "direct",
                    "path": f"{hypothesis.from_} -> {hypothesis.to}",
                    "statistic_id": f"effects.direct.{pair_id}",
                    "verdict": _verdict(block, sign=hypothesis.sign, rule=rule),
                    "rule_id": str(rule["rule_id"]),
                }
            )
        elif hypothesis.effect == "indirect":
            via = tuple(hypothesis.via or [])
            row = indirect_rows.get((pair[0], pair[1], via))
            if row is None:
                _missing(hypothesis.id)
            via_suffix = "via_" + "_".join(via)
            rows.append(
                {
                    "hypothesis": hypothesis.id,
                    "effect": "indirect",
                    "path": " -> ".join([hypothesis.from_, *via, hypothesis.to]),
                    "statistic_id": f"effects.indirect.{pair_id}.{via_suffix}",
                    "classification_id": f"effects.classification.{pair_id}.{via_suffix}",
                    "verdict": _verdict(row["indirect"], sign=hypothesis.sign, rule=rule),
                    "rule_id": str(rule["rule_id"]),
                }
            )
        else:
            block = total_blocks.get(pair)
            if block is None:
                _missing(hypothesis.id)
            rows.append(
                {
                    "hypothesis": hypothesis.id,
                    "effect": "total",
                    "path": f"{hypothesis.from_} -> {hypothesis.to}",
                    "statistic_id": f"effects.total.{pair_id}",
                    "verdict": _verdict(block, sign=hypothesis.sign, rule=rule),
                    "rule_id": str(rule["rule_id"]),
                }
            )
    return rows
