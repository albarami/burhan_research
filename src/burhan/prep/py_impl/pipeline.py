"""The Python preparation pipeline (FR-501/502/506; PB-02/03/04).

Sequence (PB-02 order, every operational value from policy paths):
consent → duplicates (policy keys, drop-later-keep-first) → attention
checks → straight-liners (zero variance within a contiguous answered run
of ≥ policy block length, instrument order) → completion profiling with
partial recovery at the policy threshold → range enforcement → reverse
coding (with sign-flip screening) → missingness mechanism + policy-driven
treatment selection → outlier assessment (policy criteria and treatment).

Design decisions this module records deliberately:

- **Out-of-range cells become missing, cases stay.** FR-506's chain
  enumerates no range link, and invariant I1 must hold post-prep; a
  corrupt cell is detected (case + item, never the value) and nulled, and
  the missing-data treatment owns it from there.
- **The missing-cell census is taken on the profiled sample before range
  enforcement**, so engineered missingness and range-nulled cells stay
  distinguishable classes (AT-M08-1).
- **Case keys** are the export's id values; a repeated id gets an
  occurrence suffix (``R_001#2``) so the N-chain accounts row-level
  identity exactly while artifacts stay readable.
- **No cell is ever filled and no case is ever fabricated** (FR-505):
  FIML/MI happen at estimation; preparation selects and logs only.
- **The invariant gate is a separate call** (``prep.invariants``): the
  golden run reports every detection class while AT-M08-8's un-reversed
  item halts at ``assert_invariants`` — detection and gate are distinct
  duties.

Artifacts carry case IDs, item codes, counts, and percentages — never
respondent values (halt reports likewise).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

# Untyped third-party edges (no stubs in the locked dependency set).
import pandas as pd  # type: ignore[import-untyped]
from scipy import stats  # type: ignore[import-untyped]

# Direct integration with the TC-05 ingest accounting: the crosswalk owns
# format/dialect loading; re-implementing it here would drift (FR-501).
from burhan.contract.crosswalk import ROLE_MODEL_ITEM, _load_raw, build_crosswalk
from burhan.core.errors import IntegrityHalt, halt
from burhan.prep.n_chain import NChain, NChainAccountant
from burhan.prep.py_impl.missingness import missingness_report

if TYPE_CHECKING:
    from pathlib import Path

    from burhan.core.artifacts.models import StudyConfig
    from burhan.core.policy import Policy

_CONSENT_GIVEN = "1"


@dataclass(frozen=True)
class PrepResult:
    """Everything preparation produced: frame plus the account of it."""

    frame: pd.DataFrame
    n_chain: NChain
    screening: dict[str, Any]
    completion_profile: dict[str, Any]
    missingness: dict[str, Any]
    outliers: dict[str, Any]


def _case_keys(rows: list[list[str]], id_index: int) -> list[str]:
    """Export id values, occurrence-suffixed on repeats (row-level identity)."""
    seen: dict[str, int] = {}
    keys = []
    for row in rows:
        raw_id = row[id_index]
        seen[raw_id] = seen.get(raw_id, 0) + 1
        keys.append(raw_id if seen[raw_id] == 1 else f"{raw_id}#{seen[raw_id]}")
    return keys


def _straightline_run(values: list[float | None], minimum: int) -> bool:
    """Zero variance across a contiguous run of >= minimum answered items."""
    run_value: float | None = None
    run_length = 0
    for value in values:
        if value is None:
            run_value, run_length = None, 0
            continue
        if value == run_value:
            run_length += 1
        else:
            run_value, run_length = value, 1
        if run_length >= minimum:
            return True
    return False


def run_prep(
    export_path: Path,
    config: StudyConfig,
    policy: Policy,
    *,
    mcar_alpha: float = 0.05,
    treatment_select: str = "primary",
) -> PrepResult:
    """Run the full Python preparation sequence; every count accounted for."""
    crosswalk = build_crosswalk(export_path, config)
    header_rows = crosswalk.header_rows
    raw_rows = _load_raw(export_path, str(config.data.format))
    codes = raw_rows[0]
    data_rows = raw_rows[header_rows:]

    id_column = config.data.id_column
    if id_column is None or id_column not in codes:
        halt(
            IntegrityHalt(
                "preparation requires a declared id column",
                report={"file": export_path.name},
            )
        )
    id_index = codes.index(id_column)
    keys = _case_keys(data_rows, id_index)
    by_key = dict(zip(keys, data_rows, strict=True))

    item_order = [item.code for item in config.instrument.items]
    column_of = {item: column for column, item in crosswalk.column_to_item.items()}
    item_index = {item: codes.index(column_of[item]) for item in item_order}
    scale_of = {item.code: item.scale for item in config.instrument.items}

    accountant = NChainAccountant(keys)
    screening: dict[str, list[dict[str, str]]] = {
        "non_consent": [],
        "duplicates": [],
        "attention_fails": [],
        "straight_liners": [],
        "missing_cells": [],
        "items_missing_over_policy_pct": [],
        "out_of_range": [],
        "reverse_coding_violations": [],
    }
    current = list(keys)

    # -- consent (PB-02 sequence head; structural, not policy-tunable) ----------
    if config.data.consent_column is not None:
        consent_index = codes.index(config.data.consent_column)
        refused = [key for key in current if by_key[key][consent_index] != _CONSENT_GIVEN]
        screening["non_consent"] = [{"case": key} for key in refused]
        accountant.apply("consent", dropped=refused)
        current = [key for key in current if key not in set(refused)]
    else:
        accountant.apply("consent")

    # -- duplicates (policy keys; drop later, keep first) ------------------------
    duplicate_keys = [str(k) for k in policy.rule("prep.duplicates.keys")]
    dropped_dupes: list[str] = []
    if "response_id" in duplicate_keys:
        seen_ids: set[str] = set()
        for key in current:
            raw_id = by_key[key][id_index]
            if raw_id in seen_ids:
                dropped_dupes.append(key)
                screening["duplicates"].append({"case": key, "kind": "response_id"})
            else:
                seen_ids.add(raw_id)
    if "identical_model_vector" in duplicate_keys:
        seen_vectors: dict[tuple[str, ...], str] = {}
        for key in current:
            if key in set(dropped_dupes):
                continue
            vector = tuple(by_key[key][item_index[item]] for item in item_order)
            if vector in seen_vectors:
                dropped_dupes.append(key)
                screening["duplicates"].append({"case": key, "kind": "identical_model_vector"})
            else:
                seen_vectors[vector] = key
    accountant.apply("duplicates", dropped=dropped_dupes)
    current = [key for key in current if key not in set(dropped_dupes)]

    # -- attention checks (policy action) ----------------------------------------
    attention_action = str(policy.rule("prep.attention_checks.action_on_fail"))
    failed_attention: list[str] = []
    for check in config.data.attention_checks or []:
        check_index = codes.index(check.column)
        for key in current:
            if key in set(failed_attention):
                continue
            if by_key[key][check_index] != check.expected:
                failed_attention.append(key)
                screening["attention_fails"].append({"case": key, "column": check.column})
    accountant.apply(
        "attention_checks",
        dropped=failed_attention if attention_action == "drop" else (),
    )
    if attention_action == "drop":
        current = [key for key in current if key not in set(failed_attention)]

    # -- straight-liners (policy method + block length) ---------------------------
    method = str(policy.rule("prep.straightliner.method"))
    block_length = int(policy.rule("prep.straightliner.min_block_length"))
    liner_action = str(policy.rule("prep.straightliner.action"))
    if method != "zero_variance_within_block":
        halt(
            IntegrityHalt(
                "unsupported straight-liner method in policy",
                report={"method": method},
            )
        )

    def answered(key: str, item: str) -> float | None:
        cell = by_key[key][item_index[item]].strip()
        if cell == "":
            return None
        try:
            return float(cell)
        except ValueError:
            return None

    liners = [
        key
        for key in current
        if _straightline_run([answered(key, item) for item in item_order], block_length)
    ]
    screening["straight_liners"] = [{"case": key} for key in liners]
    accountant.apply("straight_liners", dropped=liners if liner_action == "drop" else ())
    if liner_action == "drop":
        current = [key for key in current if key not in set(liners)]

    # -- missing-cell census on the profiled sample (before range nulling) --------
    for key in current:
        for item in item_order:
            if by_key[key][item_index[item]].strip() == "":
                screening["missing_cells"].append({"case": key, "item": item})
    flag_pct = float(policy.rule("prep.item_missing_flag_pct"))
    for item in item_order:
        missing_n = sum(1 for e in screening["missing_cells"] if e["item"] == item)
        if current and 100.0 * missing_n / len(current) > flag_pct:
            screening["items_missing_over_policy_pct"].append(
                {"item": item, "missing_n": str(missing_n)}
            )

    # -- completion profiling and partial recovery (policy threshold) -------------
    threshold = float(policy.rule("prep.inclusion_threshold.min_completion_pct"))
    basis = str(policy.rule("prep.inclusion_threshold.basis"))
    if basis != "model_items":
        halt(
            IntegrityHalt(
                "unsupported completion basis in policy",
                report={"basis": basis},
            )
        )
    partials: list[dict[str, Any]] = []
    dropped_partials: list[str] = []
    recovered_partials: list[str] = []
    for key in current:
        answered_n = sum(1 for item in item_order if by_key[key][item_index[item]].strip() != "")
        pct = 100.0 * answered_n / len(item_order)
        if pct >= 100.0:
            continue
        disposition = "recovered" if pct >= threshold else "dropped"
        partials.append({"case": key, "completion_pct": round(pct, 2), "disposition": disposition})
        (recovered_partials if disposition == "recovered" else dropped_partials).append(key)
    accountant.apply("partial_recovery", dropped=dropped_partials, recovered=recovered_partials)
    current = [key for key in current if key not in set(dropped_partials)]
    completion_profile = {
        "threshold_pct": threshold if threshold % 1 else int(threshold),
        "basis": basis,
        "partials": partials,
    }

    # -- typed frame, range enforcement, reverse coding ---------------------------
    values: dict[str, list[float]] = {item: [] for item in item_order}
    for key in current:
        for item in item_order:
            cell = by_key[key][item_index[item]].strip()
            scale = scale_of[item]
            if cell == "":
                values[item].append(math.nan)
                continue
            try:
                number = float(cell)
            except ValueError:
                number = math.nan
                screening["out_of_range"].append({"case": key, "item": item})
                values[item].append(number)
                continue
            if number < scale.min or number > scale.max:
                screening["out_of_range"].append({"case": key, "item": item})
                values[item].append(math.nan)
            else:
                values[item].append(number)
    frame = pd.DataFrame(values, index=pd.Index(current, name="case"), dtype=float)
    for item in item_order:
        scale = scale_of[item]
        if next(i for i in config.instrument.items if i.code == item).reverse_coded:
            frame[item] = (scale.min + scale.max) - frame[item]

    # sign-flip screening (detection twin of invariant I2, AT-M08-1)
    indicators = {c.code: list(c.indicators or []) for c in config.constructs}
    for instrument_item in config.instrument.items:
        if not instrument_item.reverse_coded:
            continue
        siblings = [
            code
            for code in indicators.get(instrument_item.construct_ref, [])
            if code != instrument_item.code and code in frame.columns
        ]
        if not siblings:
            continue
        correlation = frame[instrument_item.code].corr(frame[siblings].mean(axis=1))
        if not correlation > 0:
            screening["reverse_coding_violations"].append({"item": instrument_item.code})

    # -- missingness mechanism + policy treatment (FR-503/504) --------------------
    missingness = missingness_report(frame, policy, alpha=mcar_alpha, select=treatment_select)

    # -- outliers (policy criteria; policy treatment) ------------------------------
    z_criterion = float(policy.rule("prep.outliers.univariate_z"))
    mahalanobis_p = float(policy.rule("prep.outliers.mahalanobis_p"))
    treatment = str(policy.rule("prep.outliers.treatment"))
    flagged: dict[str, list[str]] = {}
    means = frame.mean()
    sds = frame.std(ddof=1)
    for item in item_order:
        if not sds[item] > 0:
            continue
        z_scores = (frame[item] - means[item]) / sds[item]
        for key in frame.index[z_scores.abs() > z_criterion]:
            flagged.setdefault(str(key), []).append(f"univariate:{item}")
    complete = frame.dropna()
    if len(complete) > len(frame.columns):
        centered = complete.to_numpy() - complete.to_numpy().mean(axis=0)
        covariance = np.cov(centered, rowvar=False)
        inverse = np.linalg.pinv(covariance)
        d2 = np.einsum("ij,jk,ik->i", centered, inverse, centered)
        criterion = float(stats.chi2.ppf(1.0 - mahalanobis_p, df=frame.shape[1]))
        for key, distance in zip(complete.index, d2, strict=True):
            if distance > criterion:
                flagged.setdefault(str(key), []).append("mahalanobis")
    flagged_entries = [
        {"case": key, "criteria": sorted(set(reasons))} for key, reasons in sorted(flagged.items())
    ]
    if treatment == "retain_with_sensitivity":
        outlier_drops: list[str] = []
    elif treatment == "remove_with_sensitivity":
        outlier_drops = sorted(flagged)
    else:
        halt(
            IntegrityHalt(
                "unsupported outlier treatment in policy",
                report={"treatment": treatment},
            )
        )
    accountant.apply("outlier_policy", dropped=outlier_drops)
    if outlier_drops:
        frame = frame.drop(index=outlier_drops)
    outliers = {
        "flagged": flagged_entries,
        "univariate_z": z_criterion,
        "mahalanobis_p": mahalanobis_p,
        "treatment": treatment,
        "sensitivity_comparison_required": bool(flagged_entries),
    }

    chain = accountant.finalize()
    if list(frame.index) != list(chain.final_cases):
        halt(
            IntegrityHalt(
                "prepared frame and N-chain disagree on the final sample (FR-506)",
                report={"frame_n": len(frame), "chain_n": chain.final_n},
            )
        )
    return PrepResult(
        frame=frame,
        n_chain=chain,
        screening=screening,
        completion_profile=completion_profile,
        missingness=missingness,
        outliers=outliers,
    )


# The zero-orphan role accounting (every model item mapped) is the
# crosswalk's duty; ROLE_MODEL_ITEM is re-exported for the invariant gate's
# callers rather than re-deriving column roles here.
__all__ = ["PrepResult", "run_prep", "ROLE_MODEL_ITEM"]
