"""The independent Python verification path — semopy (FR-902).

Fits the contract's structural model in semopy (the second engine of
the dual-path design) and compares selected estimates against the
R-engine report within the certified parity map: structural paths and
first-order measurement loadings. Comparison semantics live in
:mod:`burhan.verify.parity`; scopes outside validated parity are
declared, never force-compared.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeGuard

from burhan.core.errors import IntegrityHalt, halt
from burhan.verify.parity import parity_check, verification_settings

if TYPE_CHECKING:
    import pandas as pd  # type: ignore[import-untyped]

    from burhan.core.artifacts.models import StudyConfig
    from burhan.core.policy import Policy

_PATH_SCOPE = "structural.paths"


def _is_finite(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def semopy_syntax(config: StudyConfig) -> str:
    """The contract's measurement + structural model in lavaan-style syntax."""
    known = {construct.code for construct in config.constructs}
    lines = [
        f"{construct.code} =~ {' + '.join(construct.indicators or [])}"
        for construct in config.constructs
        if construct.level == "first_order"
    ]
    regressions: dict[str, list[str]] = {}
    for hypothesis in config.hypotheses:
        if hypothesis.effect != "direct":
            continue
        if hypothesis.from_ not in known or hypothesis.to not in known:
            halt(
                IntegrityHalt(
                    "hypothesis references an unknown construct",
                    report={"hypothesis": hypothesis.id},
                )
            )
        regressions.setdefault(hypothesis.to, []).append(hypothesis.from_)
    if not regressions:
        halt(
            IntegrityHalt(
                "the contract declares no direct structural path",
                report={"hypotheses": len(config.hypotheses)},
            )
        )
    lines.extend(f"{lhs} ~ {' + '.join(rhs)}" for lhs, rhs in regressions.items())
    return "\n".join(lines)


def independent_estimates(frame: pd.DataFrame, config: StudyConfig) -> dict[str, Any]:
    """Fit the model in semopy; return path and loading estimates."""
    import semopy  # type: ignore[import-untyped]  # local to the verification lane

    items = [item.code for item in config.instrument.items if item.code in frame.columns]
    missing = [item.code for item in config.instrument.items if item.code not in frame.columns]
    if missing:
        halt(
            IntegrityHalt(
                "verification frame lacks designed items",
                report={"missing": missing},
            )
        )
    data = frame[items].dropna()
    model = semopy.Model(semopy_syntax(config))
    model.fit(data)
    estimates = model.inspect()
    paths: dict[tuple[str, str], float] = {}
    loadings: dict[tuple[str, str], float] = {}
    constructs = {construct.code for construct in config.constructs}
    for _, row in estimates.iterrows():
        value = row["Estimate"]
        if not _is_finite(value):
            halt(
                IntegrityHalt(
                    "semopy produced a nonfinite estimate",
                    report={"lval": str(row["lval"]), "rval": str(row["rval"])},
                )
            )
        if row["op"] == "~" and row["rval"] in constructs and row["lval"] in constructs:
            paths[(str(row["lval"]), str(row["rval"]))] = float(value)
        elif row["op"] == "~" and row["rval"] in constructs:
            # semopy writes loadings as item ~ construct
            loadings[(str(row["rval"]), str(row["lval"]))] = float(value)
    return {"paths": paths, "loadings": loadings}


def _validated_paths(structural_report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """FR-902 input integrity: the engine path rows this lane compares."""
    paths = structural_report.get("paths")
    if not isinstance(paths, list):
        halt(
            IntegrityHalt(
                "structural report paths is not a list",
                report={"field": "paths"},
            )
        )
    for index, row in enumerate(paths):
        if not isinstance(row, Mapping):
            halt(
                IntegrityHalt(
                    "structural report path row is not a mapping",
                    report={"field": "paths", "index": index},
                )
            )
        for field in ("lhs", "rhs"):
            if not isinstance(row.get(field), str):
                halt(
                    IntegrityHalt(
                        f"structural report path {field} is not a string",
                        report={"field": field, "index": index},
                    )
                )
        if not _is_finite(row.get("est")):
            halt(
                IntegrityHalt(
                    "structural report path est is not a finite number",
                    report={
                        "field": "est",
                        "index": index,
                        "lhs": row["lhs"],
                        "rhs": row["rhs"],
                    },
                )
            )
    return paths


def run_verification(
    frame: pd.DataFrame,
    config: StudyConfig,
    structural_report: Mapping[str, Any],
    *,
    parity_map: Mapping[str, Any],
    policy: Policy,
) -> dict[str, Any]:
    """FR-902: compare engine estimates against semopy within parity."""
    settings = verification_settings(policy)
    paths = _validated_paths(structural_report)
    independent = independent_estimates(frame, config)
    pairs: list[dict[str, Any]] = []
    for path in paths:
        key = (path["lhs"], path["rhs"])
        if key not in independent["paths"]:
            halt(
                IntegrityHalt(
                    "independent fit lacks a structural path the engine reported",
                    report={"lhs": key[0], "rhs": key[1]},
                )
            )
        pairs.append(
            {
                "scope": _PATH_SCOPE,
                "id": f"structural.path.{key[1]}->{key[0]}",
                "engine_value": float(path["est"]),
                "independent_value": independent["paths"][key],
            }
        )
    outcome = parity_check(pairs, parity_map=parity_map, settings=settings)
    return {
        "scopes_checked": sorted({pair["scope"] for pair in pairs}),
        "results": outcome["results"],
        "flags": outcome["flags"],
    }
