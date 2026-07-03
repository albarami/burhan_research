"""Structural estimation and fit reporting (FR-801/803; PB-15/16).

The structural model comes from the contract: measurement structure
plus one regression per direct hypothesis. Global fit is evaluated
against the PB-15 bands and recorded with the step's governed
``failure_action`` (report) — no code path feeds a fit result back
into the model. The declared higher-order carrier (full hierarchy vs
latent scores, FR-803) is passed to the worker, validated on the way
back, and recorded with its rationale and citation.

All thresholds and tier bounds are parsed from the governed playbook;
every worker result block is validated with typed halts.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeGuard

from burhan.core.errors import IntegrityHalt, halt
from burhan.stats.measurement import build_measurement_payload

if TYPE_CHECKING:
    import pandas as pd  # type: ignore[import-untyped]

    from burhan.core.artifacts.models import StudyConfig
    from burhan.core.playbook import Playbook
    from burhan.core.rworker import RWorker

_CFI_GOOD_RULE = re.compile(r">=\s*(\d\.\d+)\s+good")
_RMSEA_GOOD_RULE = re.compile(r"<=\s*(\d\.\d+)\s+good")
_BAND_CRITERIA = ("normed_chisq", "cfi_floor", "tli_floor", "rmsea_ceiling", "srmr_ceiling")
_FIT_NUMERIC_KEYS = (
    "chisq",
    "cfi",
    "tli",
    "rmsea",
    "rmsea_ci_lower",
    "rmsea_ci_upper",
    "srmr",
)


def _is_number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def fit_bands(playbook: Playbook) -> dict[str, Any]:
    """PB-15 thresholds, tier bounds, and failure action — all governed."""
    criteria = {str(criterion.get("name")): criterion for criterion in playbook.criteria("PB-15")}
    values: dict[str, Any] = {}
    for name in _BAND_CRITERIA:
        criterion = criteria.get(name)
        value = criterion.get("value") if criterion is not None else None
        if not _is_number(value):
            halt(
                IntegrityHalt(
                    f"PB-15 does not state a numeric {name}",
                    report={"step": "PB-15", "criterion": name},
                )
            )
        values[name] = float(value)
    cfi_good = _CFI_GOOD_RULE.search(str(criteria["cfi_floor"].get("rule", "")))
    rmsea_good = _RMSEA_GOOD_RULE.search(str(criteria["rmsea_ceiling"].get("rule", "")))
    if cfi_good is None or rmsea_good is None:
        halt(
            IntegrityHalt(
                "PB-15 rule text does not state the good tier bound",
                report={
                    "step": "PB-15",
                    "criterion": "cfi_floor" if cfi_good is None else "rmsea_ceiling",
                },
            )
        )
    action = playbook.step("PB-15").get("failure_action")
    if not isinstance(action, str) or not action:
        halt(
            IntegrityHalt(
                "PB-15 does not declare a failure_action",
                report={"step": "PB-15"},
            )
        )
    values["cfi_good"] = float(cfi_good.group(1))
    values["rmsea_good"] = float(rmsea_good.group(1))
    values["action"] = action
    return values


def evaluate_fit_bands(fit: Mapping[str, Any], *, bands: Mapping[str, Any]) -> dict[str, Any]:
    """PB-15 band verdicts as a pure report — never touches the model."""
    entries: list[dict[str, Any]] = []
    df = fit["df"]
    if df > 0:
        normed = float(fit["chisq"]) / float(df)
        entries.append(
            {
                "criterion": "normed_chisq",
                "observed": normed,
                "threshold": bands["normed_chisq"],
                "verdict": "pass" if normed < bands["normed_chisq"] else "fail",
            }
        )
    else:
        entries.append(
            {
                "criterion": "normed_chisq",
                "observed": None,
                "threshold": bands["normed_chisq"],
                "verdict": "not_applicable",
            }
        )
    cfi = float(fit["cfi"])
    if cfi >= bands["cfi_good"]:
        cfi_verdict = "good"
    elif cfi > bands["cfi_floor"]:
        cfi_verdict = "acceptable"
    else:
        cfi_verdict = "fail"
    entries.append(
        {
            "criterion": "cfi_floor",
            "observed": cfi,
            "threshold": bands["cfi_floor"],
            "verdict": cfi_verdict,
        }
    )
    tli = float(fit["tli"])
    entries.append(
        {
            "criterion": "tli_floor",
            "observed": tli,
            "threshold": bands["tli_floor"],
            "verdict": "pass" if tli > bands["tli_floor"] else "fail",
        }
    )
    rmsea = float(fit["rmsea"])
    if rmsea <= bands["rmsea_good"]:
        rmsea_verdict = "good"
    elif rmsea < bands["rmsea_ceiling"]:
        rmsea_verdict = "acceptable"
    else:
        rmsea_verdict = "fail"
    entries.append(
        {
            "criterion": "rmsea_ceiling",
            "observed": rmsea,
            "threshold": bands["rmsea_ceiling"],
            "verdict": rmsea_verdict,
            "ci": [float(fit["rmsea_ci_lower"]), float(fit["rmsea_ci_upper"])],
        }
    )
    srmr = float(fit["srmr"])
    entries.append(
        {
            "criterion": "srmr_ceiling",
            "observed": srmr,
            "threshold": bands["srmr_ceiling"],
            "verdict": "pass" if srmr < bands["srmr_ceiling"] else "fail",
        }
    )
    return {"action": bands["action"], "entries": entries}


def build_structural_payload(frame: pd.DataFrame, config: StudyConfig) -> dict[str, Any]:
    """The worker payload: measurement structure + contract regressions."""
    known = {construct.code for construct in config.constructs}
    regressions: list[dict[str, str]] = []
    for hypothesis in config.hypotheses:
        if hypothesis.effect != "direct":
            continue
        if hypothesis.from_ not in known or hypothesis.to not in known:
            halt(
                IntegrityHalt(
                    "hypothesis references an unknown construct",
                    report={
                        "hypothesis": hypothesis.id,
                        "from": hypothesis.from_,
                        "to": hypothesis.to,
                    },
                )
            )
        regressions.append({"lhs": hypothesis.to, "rhs": hypothesis.from_})
    if not regressions:
        halt(
            IntegrityHalt(
                "the contract declares no direct structural path",
                report={"hypotheses": len(config.hypotheses)},
            )
        )
    approach = str(config.higher_order.approach) if config.higher_order is not None else None
    payload = build_measurement_payload(frame, config, approach=approach)
    payload["op"] = "sem"
    payload["carrier"] = (
        str(config.higher_order.structural_carry) if config.higher_order is not None else None
    )
    payload["regressions"] = regressions
    return payload


def _validate_fit(block: object) -> dict[str, Any]:
    if not isinstance(block, Mapping):
        halt(
            IntegrityHalt(
                "structural worker result lacks a fit block",
                report={"block": "fit"},
            )
        )
    df = block.get("df")
    if not _is_number(df) or int(df) != df or int(df) < 0:
        halt(
            IntegrityHalt(
                "structural fit df is not a non-negative integer",
                report={"field": "df"},
            )
        )
    for key in _FIT_NUMERIC_KEYS:
        if not _is_number(block.get(key)):
            halt(
                IntegrityHalt(
                    f"structural fit carries a nonnumeric {key}",
                    report={"field": key},
                )
            )
    p_value = block.get("pvalue")
    if p_value is None:
        if int(df) != 0:
            halt(
                IntegrityHalt(
                    "structural fit pvalue is missing on a testable model",
                    report={"field": "pvalue", "df": int(df)},
                )
            )
    elif not _is_number(p_value):
        halt(
            IntegrityHalt(
                "structural fit carries a nonnumeric pvalue",
                report={"field": "pvalue"},
            )
        )
    validated: dict[str, Any] = {key: float(block[key]) for key in _FIT_NUMERIC_KEYS}
    validated["df"] = int(df)
    validated["pvalue"] = None if p_value is None else float(p_value)
    return validated


def _validate_paths(block: object) -> list[dict[str, Any]]:
    if not isinstance(block, list):
        halt(
            IntegrityHalt(
                "structural worker paths block is not a list",
                report={"block": "paths"},
            )
        )
    validated: list[dict[str, Any]] = []
    for entry in block:
        if not isinstance(entry, Mapping) or not all(
            isinstance(entry.get(key), str) for key in ("lhs", "rhs")
        ):
            halt(
                IntegrityHalt(
                    "structural paths entry is malformed",
                    report={"block": "paths"},
                )
            )
        for key in ("est", "std", "se"):
            if not _is_number(entry.get(key)):
                halt(
                    IntegrityHalt(
                        f"structural paths entry carries a nonnumeric {key}",
                        report={"lhs": str(entry["lhs"]), "rhs": str(entry["rhs"])},
                    )
                )
        p_value = entry.get("p")
        if p_value is not None and not _is_number(p_value):
            halt(
                IntegrityHalt(
                    "structural paths entry carries a nonnumeric p",
                    report={"lhs": str(entry["lhs"]), "rhs": str(entry["rhs"])},
                )
            )
        validated.append(dict(entry))
    return validated


def _validate_model(block: object) -> dict[str, Any]:
    if not isinstance(block, Mapping):
        halt(
            IntegrityHalt(
                "structural worker result lacks a model block",
                report={"block": "model"},
            )
        )
    syntax = block.get("syntax")
    if not isinstance(syntax, str) or not syntax.strip():
        halt(
            IntegrityHalt(
                "structural model syntax is missing or blank",
                report={"field": "syntax"},
            )
        )
    nfree = block.get("nfree")
    if not _is_number(nfree) or int(nfree) != nfree or int(nfree) <= 0:
        halt(
            IntegrityHalt(
                "structural model nfree is not a positive integer",
                report={"field": "nfree"},
            )
        )
    return {"syntax": syntax, "nfree": int(nfree)}


def run_structural(
    frame: pd.DataFrame,
    config: StudyConfig,
    *,
    playbook: Playbook,
    rworker: RWorker,
    run_dir: Any,
    call_id: str,
) -> dict[str, Any]:
    """Fit the contract's structural model; report fit bands, never act."""
    bands = fit_bands(playbook)
    payload = build_structural_payload(frame, config)
    result = rworker.call("structural_worker", payload, call_id=call_id, run_dir=run_dir, seed=1)
    if not isinstance(result, Mapping):
        halt(
            IntegrityHalt(
                "structural worker result is not a mapping",
                report={"block": "result"},
            )
        )
    if result.get("carrier") != payload["carrier"]:
        halt(
            IntegrityHalt(
                "structural worker fitted a different carrier than requested",
                report={
                    "requested": str(payload["carrier"]),
                    "returned": str(result.get("carrier")),
                },
            )
        )
    fit = _validate_fit(result.get("fit"))
    paths = _validate_paths(result.get("paths"))
    model = _validate_model(result.get("model"))
    carrier_block: dict[str, Any] | None = None
    if config.higher_order is not None:
        carry = str(config.higher_order.structural_carry)
        approach = str(config.higher_order.approach)
        carrier_block = {
            "value": carry,
            "approach": approach,
            "rationale": (
                f"Declared in the study contract (higher_order.structural_carry = {carry}; "
                f"approach = {approach}); carried into the structural model per FR-803."
            ),
            "citation": config.higher_order.citation,
        }
    return {
        "carrier": carrier_block,
        "model": model,
        "fit": fit,
        "paths": paths,
        "band_evaluation": evaluate_fit_bands(fit, bands=bands),
    }
