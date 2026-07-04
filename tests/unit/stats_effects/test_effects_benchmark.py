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


# ---- engine-path benchmark (run_effects on the published ex5.11 model) ----

# Published ex5.11 path estimates (tests/unit/stats_structural/PROVENANCE.md)
EX511_PUBLISHED_PATHS = {("F3", "F1"): 0.563, ("F3", "F2"): 0.790, ("F4", "F3"): 0.473}
# Derived from published paths: indirect F1→F4 via F3 = .563 × .473
EX511_INDIRECT_EST = 0.266
# Fixed-seed bootstrap CI captured on the renv-locked stack through
# run_effects (seed 1, R = 1000, bca.simple; PROVENANCE.md)
EX511_INDIRECT_CI = {"ci_low": 0.195444, "ci_high": 0.360454}
EX511_CI_TOLERANCE = 0.005


def _run_engine(tmp_path: Path) -> dict[str, Any]:
    from effects_util import ex511_config, ex511_frame, playbook

    from burhan.stats.effects import run_effects

    return run_effects(
        ex511_frame(),
        ex511_config(),
        policy=policy_with(tmp_path, resamples=1000),
        playbook=playbook(),
        rworker=RWorker(),
        run_dir=tmp_path,
        call_id="bench-e511",
    )


def test_engine_path_reproduces_published_model(tmp_path: Path) -> None:
    # AT-M11-2 through the delivered Python engine: build_effects_payload
    # + run_effects + validation, on the published latent mediation chain
    # (no direct F1→F4 edge — exactly the published model).
    report = _run_engine(tmp_path)
    paths = {(p["lhs"], p["rhs"]): p["est"] for p in report["paths"]}
    for key, published in EX511_PUBLISHED_PATHS.items():
        assert round(paths[key], 3) == published, key
    (row,) = report["effects"]
    assert round(row["indirect"]["est"], 3) == EX511_INDIRECT_EST
    assert row["direct"] is None
    assert row["total"] is None
    assert row["classification"] == "indirect_only"
    for bound, pinned in EX511_INDIRECT_CI.items():
        assert abs(row["indirect"][bound] - pinned) <= EX511_CI_TOLERANCE, bound
    assert report["bootstrap"] == {
        "resamples": 1000,
        "completed": 1000,
        "ci_level": 0.95,
        "ci_type": "bias_corrected",
    }


def test_engine_report_flows_into_store_and_matrix(tmp_path: Path) -> None:
    # The live engine report round-trips: store rows written through the
    # real append-only ResultsStore, every matrix ID resolving.
    import datetime as dt

    from effects_util import ex511_config, playbook

    from burhan.results.store import ResultsStore
    from burhan.stats.effects import effects_store_rows
    from burhan.stats.hypothesis_matrix import build_hypothesis_matrix

    class FixedClock:
        def now(self) -> dt.datetime:
            return dt.datetime(2026, 7, 4, 12, 0, 0, tzinfo=dt.UTC)

    report = _run_engine(tmp_path)
    store = ResultsStore(tmp_path / "results", FixedClock())
    for payload in effects_store_rows(report):
        store.write(payload)
    rows = build_hypothesis_matrix(ex511_config(), report, playbook=playbook())
    indirect_rows = [row for row in rows if row["effect"] == "indirect"]
    assert [row["hypothesis"] for row in indirect_rows] == ["H4"]
    for row in indirect_rows:
        assert store.resolve(row["statistic_id"]).stage == "effects"
        assert store.resolve(row["classification_id"]).value == "indirect_only"
    assert indirect_rows[0]["verdict"] == "supported"


def test_resamples_read_from_policy(tmp_path: Path) -> None:
    # AT-M11-2: the resample count comes from the policy layer, never a
    # constant — the engine payload embeds exactly the policy value.
    policy = policy_with(tmp_path, resamples=2000)
    payload = build_effects_payload(mediation_frame(), mediation_config(), policy=policy)
    assert payload["bootstrap"]["resamples"] == 2000
    assert payload["bootstrap"]["ci_level"] == 0.95
    assert payload["bootstrap"]["ci_type"] == "bias_corrected"
