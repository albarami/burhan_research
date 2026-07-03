"""Cell-level dual-path reconciliation (FR-501; AT-M08-6).

The R and Python preparation paths are independent implementations of the
same governed sequence; this module is where they must agree. The compare
is cell-for-cell at the policy tolerance (``verification.prep_cell_tolerance``,
exactly 0 in the governed template): any divergence — a cell value, a
missing/observed mismatch, column order, the case set, or an N-chain link
count — halts ``VerificationHalt`` (HALTED_VERIFICATION) with a
discrepancy report naming the row and column. Reports never carry
respondent values (row = case id, column = item code, nothing else).

``build_r_payload`` assembles everything the R worker needs — contract
slice plus policy rules — so the R path reads the same governed values
without ever importing Python prep internals (independent-chain
discipline).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from burhan.core.errors import IntegrityHalt, VerificationHalt, halt

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from burhan.core.artifacts.models import StudyConfig
    from burhan.core.policy import Policy
    from burhan.prep.py_impl.pipeline import PrepResult


def build_r_payload(csv_path: Path, config: StudyConfig, policy: Policy) -> dict[str, Any]:
    """The R prep worker's call payload: contract slice + policy rules."""
    column_of = {
        item.code: item.column_hint for item in config.instrument.items if item.column_hint
    }
    missing_hints = [item.code for item in config.instrument.items if not item.column_hint]
    if missing_hints:
        halt(
            IntegrityHalt(
                "R prep payload requires a column hint for every item",
                report={"items": missing_hints},
            )
        )
    return {
        "csv_path": str(csv_path),
        "header_rows": config.data.header_rows if config.data.header_rows is not None else 1,
        "id_column": config.data.id_column,
        "consent_column": config.data.consent_column,
        "attention_checks": [
            {"column": check.column, "expected": check.expected}
            for check in config.data.attention_checks or []
        ],
        "items": [
            {
                "code": item.code,
                "column": column_of[item.code],
                "min": item.scale.min,
                "max": item.scale.max,
                "reverse": item.reverse_coded,
            }
            for item in config.instrument.items
        ],
        "policy": {
            "duplicate_keys": [str(k) for k in policy.rule("prep.duplicates.keys")],
            "attention_action": str(policy.rule("prep.attention_checks.action_on_fail")),
            "straightliner_method": str(policy.rule("prep.straightliner.method")),
            "straightliner_min_block": int(policy.rule("prep.straightliner.min_block_length")),
            "straightliner_action": str(policy.rule("prep.straightliner.action")),
            "min_completion_pct": policy.rule("prep.inclusion_threshold.min_completion_pct"),
            "completion_basis": str(policy.rule("prep.inclusion_threshold.basis")),
            "univariate_z": policy.rule("prep.outliers.univariate_z"),
            "mahalanobis_p": policy.rule("prep.outliers.mahalanobis_p"),
            "outlier_treatment": str(policy.rule("prep.outliers.treatment")),
        },
    }


def _discrepancy(kind: str, **named: str) -> None:
    halt(
        VerificationHalt(
            "dual-path preparation discrepancy (FR-501): unexplained "
            "difference between the Python and R implementations",
            report={"kind": kind, **named},
        )
    )


def reconcile_prep(
    python_result: PrepResult, r_result: Mapping[str, Any], *, policy: Policy
) -> dict[str, Any]:
    """Diff the two prepared frames at the policy tolerance (exactly 0).

    Returns the parity report on a full match; halts ``VerificationHalt``
    on the first divergence, naming what diverged (row/column for cells)
    and never carrying respondent values.
    """
    tolerance = float(policy.rule("verification.prep_cell_tolerance"))
    frame = python_result.frame
    py_columns = [str(column) for column in frame.columns]
    r_columns = [str(column) for column in r_result.get("columns", [])]
    if py_columns != r_columns:
        _discrepancy("columns")
    py_cases = [str(case) for case in frame.index]
    r_cases = [str(case) for case in r_result.get("cases", [])]
    if py_cases != r_cases:
        _discrepancy("cases")

    r_cells = r_result.get("cells", [])
    if len(r_cells) != len(py_cases):
        _discrepancy("cases")
    py_matrix = frame.to_numpy().tolist()
    for row_index, case in enumerate(py_cases):
        py_row = py_matrix[row_index]
        r_row = r_cells[row_index]
        if len(r_row) != len(py_columns):
            _discrepancy("columns")
        for column_index, column in enumerate(py_columns):
            py_value = py_row[column_index]
            r_value = r_row[column_index]
            py_missing = isinstance(py_value, float) and math.isnan(py_value)
            r_missing = r_value is None or (isinstance(r_value, float) and math.isnan(r_value))
            if py_missing and r_missing:
                continue
            if py_missing != r_missing:
                halt(
                    VerificationHalt(
                        "dual-path preparation discrepancy (FR-501): "
                        "missing/observed cell mismatch",
                        report={"kind": "cell", "row": case, "column": column},
                    )
                )
            if abs(float(py_value) - float(r_value)) > tolerance:
                halt(
                    VerificationHalt(
                        "dual-path preparation discrepancy (FR-501): cell "
                        "divergence beyond tolerance",
                        report={"kind": "cell", "row": case, "column": column},
                    )
                )

    py_chain = {link.name: link.dropped_n for link in python_result.n_chain.links}
    r_chain_block = r_result.get("n_chain", {})
    r_chain = {
        str(name): int(count)
        for name, count in dict(r_chain_block.get("dropped_by_link", {})).items()
    }
    if (
        py_chain != r_chain
        or int(r_chain_block.get("raw_n", -1)) != python_result.n_chain.raw_n
        or int(r_chain_block.get("final_n", -1)) != python_result.n_chain.final_n
    ):
        diverging = sorted(
            name for name in set(py_chain) | set(r_chain) if py_chain.get(name) != r_chain.get(name)
        )
        halt(
            VerificationHalt(
                "dual-path preparation discrepancy (FR-501): N-chain "
                "accounting differs between implementations",
                report={"kind": "n_chain", "links": diverging or ["raw_n/final_n"]},
            )
        )
    return {
        "verdict": "match",
        "tolerance": int(tolerance) if tolerance == int(tolerance) else tolerance,
        "cells_compared": len(py_cases) * len(py_columns),
        "cases": len(py_cases),
        "columns": len(py_columns),
    }
