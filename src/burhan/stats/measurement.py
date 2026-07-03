"""Measurement stage: CFA, validity, CMB (FR-701–704; PB-08–PB-12).

The R worker (lavaan/semTools, renv-locked) is the authoritative engine;
this module builds the payload from the contract, validates every block
of the worker result before use (typed halts, no raw dereference, no
catch-and-continue), and evaluates the governed bands:

- PB-09: loading target .708, borderline floor .70 (both parsed from the
  criterion, never literals);
- PB-10: alpha/CR floors .70, AVE floor .50;
- PB-11: Fornell–Larcker plus HTMT bands — pass ≤ .85 < flag ≤ .90 < fail;
- PB-12: Harman is a screen only; the CLF/marker comparison is the
  substantive test, and an evaluation without it is never complete. The
  step's single governed bound (0.50) is the share line for the screen
  and the substantive method-variance share alike; loading distortions
  are reported as evidence (PB-12 defines no distortion bound).

Both higher-order approaches are first-class (FR-701): repeated-indicator
(one fit) and two-stage (correlated first-order CFA, then the L2 factor
on stage-1 factor scores). Reporting always covers both levels (FR-702);
a worker report missing a required level halts.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, TypeGuard

from burhan.core.errors import IntegrityHalt, halt

if TYPE_CHECKING:
    import pandas as pd  # type: ignore[import-untyped]

    from burhan.core.artifacts.models import StudyConfig
    from burhan.core.playbook import Playbook
    from burhan.core.policy import Policy
    from burhan.core.rworker import RWorker

_BORDERLINE_RULE = re.compile(r"(\d\.\d+)\s*[–-]\s*(\d\.\d+)\s*borderline")
_HTMT_FAIL_RULE = re.compile(r">\s*(\d\.\d+)\s*fails")


def _criterion(playbook: Playbook, step: str, name: str) -> dict[str, Any]:
    for criterion in playbook.criteria(step):
        if criterion.get("name") == name:
            return criterion
    halt(
        IntegrityHalt(
            f"playbook {step} lacks the {name} criterion",
            report={"criteria": [c.get("name") for c in playbook.criteria(step)]},
        )
    )


def measurement_bands(playbook: Playbook) -> dict[str, float]:
    """Every governed measurement band, parsed from the playbook."""
    loading = _criterion(playbook, "PB-09", "loading_target")
    borderline = _BORDERLINE_RULE.search(str(loading.get("rule", "")))
    if borderline is None:
        halt(
            IntegrityHalt(
                "PB-09 loading_target rule lacks a parseable borderline band",
                report={"rule": str(loading.get("rule"))},
            )
        )
    htmt = _criterion(playbook, "PB-11", "htmt_ceiling")
    fail_match = _HTMT_FAIL_RULE.search(str(htmt.get("rule", "")))
    if fail_match is None:
        halt(
            IntegrityHalt(
                "PB-11 htmt_ceiling rule lacks a parseable fail bound",
                report={"rule": str(htmt.get("rule"))},
            )
        )
    return {
        "loading_target": float(loading["value"]),
        "loading_borderline": float(borderline.group(1)),
        "alpha_floor": float(_criterion(playbook, "PB-10", "alpha_floor")["value"]),
        "cr_floor": float(_criterion(playbook, "PB-10", "cr_floor")["value"]),
        "ave_floor": float(_criterion(playbook, "PB-10", "ave_floor")["value"]),
        "htmt_flag": float(htmt["value"]),
        "htmt_fail": float(fail_match.group(1)),
        "harman_share": float(_criterion(playbook, "PB-12", "harman_screen")["value"]),
    }


def htmt_band(value: float, *, bands: dict[str, float]) -> str:
    """PB-11 band: pass ≤ flag bound < flag ≤ fail bound < fail."""
    if value > bands["htmt_fail"]:
        return "fail"
    if value > bands["htmt_flag"]:
        return "flag"
    return "pass"


def _is_number(value: object) -> TypeGuard[int | float]:
    return not isinstance(value, bool) and isinstance(value, int | float)


def _second_order_spec(config: StudyConfig) -> dict[str, Any] | None:
    second = [c for c in config.constructs if c.level == "second_order"]
    if not second:
        return None
    if len(second) > 1:
        halt(
            IntegrityHalt(
                "TC-10a supports exactly one second-order construct",
                report={"second_order": [c.code for c in second]},
            )
        )
    return {"code": second[0].code, "components": list(second[0].components or [])}


def build_measurement_payload(
    frame: pd.DataFrame, config: StudyConfig, *, approach: str | None
) -> dict[str, Any]:
    """The worker payload: complete cases, contract structure, approach."""
    items = [item.code for item in config.instrument.items if item.code in frame.columns]
    missing = [item.code for item in config.instrument.items if item.code not in frame.columns]
    if missing:
        halt(
            IntegrityHalt(
                "measurement frame lacks designed items",
                report={"missing": missing},
            )
        )
    complete = frame[items].dropna()
    if len(complete) <= len(items):
        halt(
            IntegrityHalt(
                "measurement needs more complete cases than indicators",
                report={"n": int(len(complete)), "items": len(items)},
            )
        )
    second = _second_order_spec(config)
    if second is not None and approach is None:
        if config.higher_order is None:
            halt(
                IntegrityHalt(
                    "second-order constructs require a declared higher-order approach",
                    report={"second_order": second["code"]},
                )
            )
        approach = str(config.higher_order.approach)
    return {
        "op": "cfa",
        "columns": items,
        "cells": [[float(v) for v in row] for row in complete.to_numpy().tolist()],
        "constructs": [
            {"code": c.code, "indicators": list(c.indicators or [])}
            for c in config.constructs
            if c.level == "first_order"
        ],
        "second_order": second,
        "approach": approach,
    }


def _require_mapping(block: object, name: str) -> dict[str, Any]:
    if not isinstance(block, dict):
        halt(
            IntegrityHalt(
                f"measurement result carries a missing or malformed {name} block",
                report={"block": name, "type": type(block).__name__},
            )
        )
    return block


def _require_list(block: object, name: str) -> list[Any]:
    if not isinstance(block, list):
        halt(
            IntegrityHalt(
                f"measurement result carries a missing or malformed {name} block",
                report={"block": name, "type": type(block).__name__},
            )
        )
    return block


def _validate_loadings(entries: object, name: str, member_key: str) -> list[dict[str, Any]]:
    validated: list[dict[str, Any]] = []
    for entry in _require_list(entries, name):
        record = _require_mapping(entry, name)
        keys = {"construct", member_key, "est", "std", "se"}
        if not keys <= set(record):
            halt(
                IntegrityHalt(
                    f"measurement {name} entry lacks required fields",
                    report={"block": name, "missing": sorted(keys - set(record))},
                )
            )
        for numeric in ("est", "std", "se"):
            if not _is_number(record[numeric]):
                halt(
                    IntegrityHalt(
                        f"measurement {name} entry carries a nonnumeric {numeric}",
                        report={"block": name, "field": numeric},
                    )
                )
        p_value = record.get("p")
        if p_value is not None and not _is_number(p_value):
            halt(
                IntegrityHalt(
                    f"measurement {name} entry carries a nonnumeric p",
                    report={"block": name},
                )
            )
        validated.append(dict(record))
    return validated


def _validate_reliability(entries: object) -> list[dict[str, Any]]:
    validated: list[dict[str, Any]] = []
    for entry in _require_list(entries, "reliability"):
        record = _require_mapping(entry, "reliability")
        for key in ("alpha", "cr", "ave"):
            value = record.get(key)
            if not _is_number(value) or not 0.0 < value <= 1.0:
                halt(
                    IntegrityHalt(
                        "measurement reliability entry is missing or out of range",
                        report={"construct": str(record.get("construct")), "field": key},
                    )
                )
        validated.append(dict(record))
    return validated


def _validate_pairs(entries: object, name: str) -> list[dict[str, Any]]:
    validated: list[dict[str, Any]] = []
    for entry in _require_list(entries, name):
        record = _require_mapping(entry, name)
        if not _is_number(record.get("value")):
            halt(
                IntegrityHalt(
                    f"measurement {name} pair carries a nonnumeric value",
                    report={"block": name},
                )
            )
        validated.append(dict(record))
    return validated


def run_measurement(
    frame: pd.DataFrame,
    config: StudyConfig,
    *,
    policy: Policy,
    playbook: Playbook,
    rworker: RWorker,
    run_dir: Any,
    call_id: str,
    approach: str | None = None,
) -> dict[str, Any]:
    """CFA + validity battery through the R worker, bands attached."""
    bands = measurement_bands(playbook)
    payload = build_measurement_payload(frame, config, approach=approach)
    result = rworker.call("measurement_worker", payload, call_id=call_id, run_dir=run_dir, seed=1)
    outer = _require_mapping(result, "measurement")

    first = _require_mapping(outer.get("first_order"), "first_order")
    first_loadings = _validate_loadings(first.get("loadings"), "first_order loadings", "item")
    first_reliability = _validate_reliability(first.get("reliability"))

    second_spec = _second_order_spec(config)
    second_report: dict[str, Any] | None = None
    if second_spec is not None:
        second = _require_mapping(outer.get("second_order"), "second_order")
        second_loadings = _validate_loadings(
            second.get("loadings"), "second_order loadings", "component"
        )
        second_reliability = _require_mapping(second.get("reliability"), "second_order reliability")
        for key in ("cr_l2", "omega_l1"):
            value = second_reliability.get(key)
            if not _is_number(value) or not 0.0 < value <= 1.0:
                halt(
                    IntegrityHalt(
                        "measurement second_order reliability is missing or out of range",
                        report={"field": key},
                    )
                )
        stage = second.get("stage")
        if stage not in (1, 2):
            halt(
                IntegrityHalt(
                    "measurement second_order stage must be 1 or 2",
                    report={"stage": repr(stage)},
                )
            )
        second_report = {
            "loadings": second_loadings,
            "reliability": dict(second_reliability),
            "stage": int(stage),
        }

    fit = _require_mapping(outer.get("fit"), "fit")
    if not _is_number(fit.get("chisq")) or not _is_number(fit.get("df")):
        halt(
            IntegrityHalt(
                "measurement fit block is missing chisq/df",
                report={"fit_keys": sorted(fit)},
            )
        )

    validity_block = _require_mapping(outer.get("validity"), "validity")
    correlations = _validate_pairs(validity_block.get("latent_correlations"), "latent_correlations")
    htmt_pairs = _validate_pairs(validity_block.get("htmt"), "htmt")

    for entry in first_loadings:
        std = abs(float(entry["std"]))
        if std >= bands["loading_target"]:
            entry["band"] = "target"
        elif std >= bands["loading_borderline"]:
            entry["band"] = "borderline"
        else:
            entry["band"] = "deletion_candidate"

    ave_by_construct = {e["construct"]: float(e["ave"]) for e in first_reliability}
    fornell: dict[str, Any] = {"constructs": [], "pass": True}
    for construct, ave in ave_by_construct.items():
        shared = [
            float(pair["value"]) ** 2
            for pair in correlations
            if construct in (pair.get("a"), pair.get("b"))
        ]
        max_shared = max(shared) if shared else 0.0
        ok = ave > max_shared
        fornell["constructs"].append(
            {"construct": construct, "ave": ave, "max_shared_variance": max_shared, "pass": ok}
        )
        fornell["pass"] = fornell["pass"] and ok

    banded_pairs = []
    worst = "pass"
    for pair in htmt_pairs:
        band = htmt_band(float(pair["value"]), bands=bands)
        banded_pairs.append({**pair, "band": band})
        if band == "fail" or (band == "flag" and worst == "pass"):
            worst = band
    if worst == "pass":
        verdict = "pass"
    else:
        offenders = ", ".join(f"{p['a']}~{p['b']}" for p in banded_pairs if p["band"] != "pass")
        verdict = f"{worst}: {offenders}"

    return {
        "approach": str(outer.get("approach")),
        "bands": bands,
        "first_order": {"loadings": first_loadings, "reliability": first_reliability},
        "second_order": second_report,
        "fit": {key: fit[key] for key in fit},
        "validity": {
            "latent_correlations": correlations,
            "fornell_larcker": fornell,
            "htmt": {"pairs": banded_pairs, "verdict": verdict},
        },
    }


def evaluate_cmb(block: object, *, playbook: Playbook) -> dict[str, Any]:
    """PB-12 evaluation: Harman screens, only the CLF completes."""
    bands = measurement_bands(playbook)
    outer = _require_mapping(block, "cmb")
    harman = outer.get("harman")
    share_value = harman.get("single_factor_share") if isinstance(harman, dict) else None
    if not _is_number(share_value):
        halt(
            IntegrityHalt(
                "cmb result carries a missing or malformed harman block",
                report={"harman": repr(harman)},
            )
        )
    share = float(share_value)
    if not 0.0 <= share <= 1.0:
        halt(
            IntegrityHalt(
                "cmb harman share out of range",
                report={"share": share},
            )
        )
    evaluation: dict[str, Any] = {
        "bands": bands,
        "harman": {
            "single_factor_share": share,
            "passes_screen": share <= bands["harman_share"],
        },
        "evidence_basis": ["harman"],
    }
    clf = outer.get("clf")
    if clf is None:
        evaluation["complete"] = False
        evaluation["incomplete_reason"] = (
            "Harman is a screen only; PB-12 requires the CLF/marker "
            "substantive test before the assessment is complete"
        )
        evaluation["clf"] = None
        return evaluation
    clf_block = _require_mapping(clf, "clf")
    method_share = clf_block.get("method_variance_share")
    if not _is_number(method_share) or not 0.0 <= method_share <= 1.0:
        halt(
            IntegrityHalt(
                "cmb clf block carries a missing or malformed method share",
                report={"method_variance_share": repr(method_share)},
            )
        )
    evaluation["clf"] = {
        "method_variance_share": float(method_share),
        "loading_distortions": clf_block.get("loading_distortions", []),
    }
    evaluation["evidence_basis"].append("clf")
    evaluation["complete"] = True
    evaluation["flagged"] = float(method_share) > bands["harman_share"]
    return evaluation


def run_cmb(
    frame: pd.DataFrame,
    config: StudyConfig,
    *,
    policy: Policy,
    playbook: Playbook,
    rworker: RWorker,
    run_dir: Any,
    call_id: str,
    marker_items: list[str] | None = None,
) -> dict[str, Any]:
    """The CMB assessment through the R worker (screen + substantive).

    ``marker_items`` names theoretically-unrelated method markers present
    in the frame (Williams et al. 2010): they anchor the CLF's
    identification — a uniform method factor without markers is
    near-equivalent to inflated trait loadings plus correlation, and the
    optimizer legitimately collapses it.
    """
    payload = build_measurement_payload(frame, config, approach=None)
    payload["op"] = "cmb"
    markers = list(marker_items or [])
    missing_markers = [m for m in markers if m not in frame.columns]
    if missing_markers:
        halt(
            IntegrityHalt(
                "cmb marker items missing from the frame",
                report={"missing": missing_markers},
            )
        )
    if markers:
        complete = frame[[*payload["columns"], *markers]].dropna()
        payload["columns"] = [*payload["columns"], *markers]
        payload["cells"] = [[float(v) for v in row] for row in complete.to_numpy().tolist()]
    payload["marker_items"] = markers
    result = rworker.call("measurement_worker", payload, call_id=call_id, run_dir=run_dir, seed=1)
    outer = _require_mapping(result, "cmb")
    if "clf" not in outer or outer.get("clf") is None:
        halt(
            IntegrityHalt(
                "cmb worker result lacks the clf substantive block",
                report={"keys": sorted(outer)},
            )
        )
    return evaluate_cmb(outer, playbook=playbook)
