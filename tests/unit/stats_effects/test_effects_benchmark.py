"""AT-M11-2: bootstrap effects reproduce the published example (FR-802/1502).

Anchor: Mplus UG ex3.16 (see PROVENANCE.md) — data committed verbatim.
Point estimates are deterministic ML and must reproduce every printed
value at printed precision; bootstrap CI bounds are resampling-
stochastic and must land within ±0.025 of the published bounds
(justification and measured deviations in PROVENANCE.md); identical
seeds must reproduce identical results byte-for-byte.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from effects_util import benchmark_frame, mediation_config, mediation_frame, policy_with

from burhan.core.rworker import RWorker
from burhan.stats.effects import bootstrap_settings, build_effects_payload

PUBLISHED_PATHS = {
    ("y1", "x1"): 0.992,
    ("y1", "x2"): 2.001,
    ("y1", "x3"): 3.052,
    ("y2", "x1"): 2.935,
    ("y2", "x2"): 1.992,
    ("y2", "x3"): 1.023,
    ("y3", "y1"): 0.507,
    ("y3", "y2"): 0.746,
    ("y3", "x2"): 1.046,
}
PUBLISHED_INDIRECT = {
    "IND1": {"est": 0.503, "ci_low": 0.445, "ci_high": 0.558},
    "IND2": {"est": 2.188, "ci_low": 2.054, "ci_high": 2.310},
}
PUBLISHED_SUM = {"est": 2.691, "ci_low": 2.567, "ci_high": 2.813}
CI_TOLERANCE = 0.025


def _payload(resamples: int, tmp_path: Path) -> dict[str, Any]:
    frame = benchmark_frame()
    policy = policy_with(tmp_path, resamples=resamples)
    settings = bootstrap_settings(policy)
    return {
        "op": "effects",
        "columns": list(frame.columns),
        "cells": [[float(v) for v in row] for row in frame.to_numpy().tolist()],
        "constructs": [],
        "second_order": None,
        "approach": None,
        "carrier": None,
        "regressions": [
            {"lhs": "y1", "rhs": "x1"},
            {"lhs": "y1", "rhs": "x2"},
            {"lhs": "y1", "rhs": "x3"},
            {"lhs": "y2", "rhs": "x1"},
            {"lhs": "y2", "rhs": "x2"},
            {"lhs": "y2", "rhs": "x3"},
            {"lhs": "y3", "rhs": "y1"},
            {"lhs": "y3", "rhs": "y2"},
            {"lhs": "y3", "rhs": "x2"},
        ],
        "indirect": [
            {"id": "IND1", "from": "x1", "to": "y3", "via": ["y1"]},
            {"id": "IND2", "from": "x1", "to": "y3", "via": ["y2"]},
        ],
        "bootstrap": settings,
    }


def _run(tmp_path: Path) -> dict[str, Any]:
    result = RWorker().call(
        "effects_worker",
        _payload(1000, tmp_path),
        call_id="bench-effects",
        run_dir=tmp_path,
        seed=1,
    )
    assert isinstance(result, dict)
    return result


def test_point_estimates_match_published(tmp_path: Path) -> None:
    result = _run(tmp_path)
    paths = {(row["lhs"], row["rhs"]): row["est"] for row in result["paths"]}
    for key, published in PUBLISHED_PATHS.items():
        assert round(paths[key], 3) == published, key
    effects = {row["id"]: row for row in result["effects"]}
    for spec_id, published_effect in PUBLISHED_INDIRECT.items():
        assert round(effects[spec_id]["indirect"]["est"], 3) == published_effect["est"], spec_id
    (total,) = result["sums"]
    assert (total["from"], total["to"]) == ("x1", "y3")
    assert round(total["est"], 3) == PUBLISHED_SUM["est"]


def test_bootstrap_cis_within_tolerance_of_published(tmp_path: Path) -> None:
    result = _run(tmp_path)
    effects = {row["id"]: row for row in result["effects"]}
    for spec_id, published_effect in PUBLISHED_INDIRECT.items():
        block = effects[spec_id]["indirect"]
        for bound in ("ci_low", "ci_high"):
            assert abs(block[bound] - published_effect[bound]) <= CI_TOLERANCE, (spec_id, bound)
    (total,) = result["sums"]
    for bound in ("ci_low", "ci_high"):
        assert abs(total[bound] - PUBLISHED_SUM[bound]) <= CI_TOLERANCE, bound
    bootstrap = result["bootstrap"]
    assert bootstrap["resamples"] == 1000
    assert bootstrap["completed"] == 1000


def test_identical_seed_reproduces_identically(tmp_path: Path) -> None:
    first = RWorker().call(
        "effects_worker", _payload(1000, tmp_path), call_id="rep-1", run_dir=tmp_path, seed=7
    )
    second = RWorker().call(
        "effects_worker", _payload(1000, tmp_path), call_id="rep-2", run_dir=tmp_path, seed=7
    )
    assert first == second


def test_resamples_read_from_policy(tmp_path: Path) -> None:
    # AT-M11-2: the resample count comes from the policy layer, never a
    # constant — the engine payload embeds exactly the policy value.
    policy = policy_with(tmp_path, resamples=2000)
    payload = build_effects_payload(mediation_frame(), mediation_config(), policy=policy)
    assert payload["bootstrap"]["resamples"] == 2000
    assert payload["bootstrap"]["ci_level"] == 0.95
    assert payload["bootstrap"]["ci_type"] == "bias_corrected"
