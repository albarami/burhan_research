"""Reference-comparison builder (FR-1503; Concept §15).

Consumes a researcher-supplied reference set and the append-only
results store; emits a schema-valid ReferenceComparisonReport. The
reference is a comparison point, not ground truth: every divergence
starts ``unresolved`` with no side presumed correct. Numeric deltas are
burhan − reference; non-numeric values compare by equality with no
delta. A reference entry naming a statistic the store does not hold is
a defect in the reference set and halts typed (via the store's own
resolve semantics).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeGuard

from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import ComparisonDomain, ReferenceComparisonReport
from burhan.core.errors import IntegrityHalt, halt

if TYPE_CHECKING:
    from burhan.results.store import ResultsStore

_SUPPORTED_DOMAINS = frozenset(domain.value for domain in ComparisonDomain)


def _is_number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _require(condition: bool, message: str, report: dict[str, Any]) -> None:
    if not condition:
        halt(IntegrityHalt(message, report=report))


def build_reference_comparison(
    reference: Mapping[str, Any],
    store: ResultsStore,
    *,
    run_id: str,
) -> dict[str, Any]:
    """Assemble and schema-validate the FR-1503 report."""
    study_id = reference.get("study_id")
    _require(
        isinstance(study_id, str) and bool(study_id),
        "reference set lacks a study_id",
        {"field": "study_id"},
    )
    source = reference.get("source")
    _require(
        isinstance(source, Mapping),
        "reference set lacks a source block",
        {"field": "source"},
    )
    entries = reference.get("entries")
    if not isinstance(entries, list) or not entries:
        halt(
            IntegrityHalt(
                "reference set declares no entries",
                report={"field": "entries"},
            )
        )
    comparisons: list[dict[str, Any]] = []
    counts = {"match": 0, "divergent": 0, "reference_missing": 0, "burhan_only": 0}
    for entry in entries:
        _require(
            isinstance(entry, Mapping),
            "reference entry is not a mapping",
            {"block": "entries"},
        )
        comparison_id = entry.get("comparison_id")
        _require(
            isinstance(comparison_id, str) and bool(comparison_id),
            "reference entry comparison_id is not a non-empty string",
            {"field": "comparison_id"},
        )
        domain = entry.get("domain")
        _require(
            isinstance(domain, str) and domain in _SUPPORTED_DOMAINS,
            "reference entry domain is not a supported comparison domain",
            {"comparison_id": comparison_id, "field": "domain"},
        )
        metric = entry.get("metric")
        _require(
            isinstance(metric, str) and bool(metric),
            "reference entry metric is not a non-empty string",
            {"comparison_id": comparison_id, "field": "metric"},
        )
        stat_id = entry.get("stat_id")
        _require(
            isinstance(stat_id, str) and bool(stat_id),
            "reference entry lacks a stat_id",
            {"comparison_id": str(entry.get("comparison_id"))},
        )
        tolerance = entry.get("tolerance", 0.0)
        _require(
            _is_number(tolerance) and math.isfinite(tolerance) and tolerance >= 0.0,
            "reference entry tolerance is not a non-negative number",
            {"comparison_id": str(entry.get("comparison_id"))},
        )
        burhan_value = store.resolve(str(stat_id)).value
        reference_value = entry.get("reference_value")
        comparison: dict[str, Any] = {
            "comparison_id": comparison_id,
            "domain": domain,
            "metric": metric,
            "burhan_value": burhan_value,
            "burhan_stat_id": str(stat_id),
        }
        if reference_value is None:
            comparison["status"] = "reference_missing"
            counts["reference_missing"] += 1
        else:
            comparison["reference_value"] = reference_value
            comparison["tolerance"] = float(tolerance)
            if _is_number(reference_value) and _is_number(burhan_value):
                delta = float(burhan_value) - float(reference_value)
                comparison["delta"] = delta
                matched = abs(delta) <= float(tolerance)
            else:
                matched = burhan_value == reference_value
            if matched:
                comparison["status"] = "match"
                counts["match"] += 1
            else:
                comparison["status"] = "divergent"
                comparison["classification"] = "unresolved"
                counts["divergent"] += 1
        comparisons.append(comparison)
    report: dict[str, Any] = {
        "schema_version": 1,
        "study_id": str(study_id),
        "run_id": run_id,
        "reference_source": dict(source),  # type: ignore[arg-type]
        "comparisons": comparisons,
        "summary": {
            "total": len(comparisons),
            "matches": counts["match"],
            "divergent": counts["divergent"],
            "reference_missing": counts["reference_missing"],
            "burhan_only": counts["burhan_only"],
            "unresolved": counts["divergent"],
        },
    }
    validate_and_build(ReferenceComparisonReport, report)
    return report
