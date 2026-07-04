"""Benchmark replication runner (AT-M12-4; FR-1502).

Replicates the published worked-example set end-to-end by invoking the
same anchor checks the benchmark/unit suites pin (single source of
truth for every reference constant), then writes the certified parity
map consumed by AT-M12-2's verification lane.

Anchors:
- Mplus UG ex5.6 (measurement: loadings, chi-square, semTools
  reliability) — tests/benchmark/higher_order_example.
- Mplus UG ex5.11 (structural: fit, paths, R²) —
  tests/unit/stats_structural.
- Mplus UG ex3.16 (effects: bootstrap indirect estimates and CIs) —
  tests/unit/stats_effects.
- MacCallum–Browne–Sugawara close-fit power (df=15, N=200 → 0.378;
  Jobst, Bader & Moshagen 2021) — certified in tests/unit/stats_power.

The map content is deterministic (no timestamps): tolerances are the
provenance-justified values from the anchor suites; re-running the
runner must reproduce the committed map byte-for-byte.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
for _extra in (
    str(REPO / "tests" / "benchmark" / "higher_order_example"),
    str(REPO / "tests" / "unit" / "stats_structural"),
    str(REPO / "tests" / "unit" / "stats_effects"),
    str(REPO / "src"),
):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

PARITY_MAP_PATH = Path(__file__).resolve().parent / "parity_map.json"

# scope -> tolerance, each justified by the named anchor's PROVENANCE
_CERTIFIED_SCOPES: dict[str, dict[str, Any]] = {
    "measurement.loadings": {"tolerance": 0.001, "anchors": ["mplus-ex5.6"]},
    "measurement.reliability": {"tolerance": 0.0001, "anchors": ["mplus-ex5.6/semtools"]},
    "structural.paths": {"tolerance": 0.001, "anchors": ["mplus-ex5.11"]},
    "structural.fit": {"tolerance": 0.001, "anchors": ["mplus-ex5.11"]},
    "structural.r_squared": {"tolerance": 0.001, "anchors": ["mplus-ex5.11/lavaan"]},
    "effects.indirect": {"tolerance": 0.001, "anchors": ["mplus-ex3.16"]},
    "effects.indirect_ci": {"tolerance": 0.025, "anchors": ["mplus-ex3.16"]},
    "power.close_fit": {"tolerance": 0.001, "anchors": ["maccallum-1996/jobst-2021"]},
}
_NON_PARITY = ["estimator.wlsmv"]


def _anchor_ex56(run_dir: Path) -> None:
    import test_higher_order_benchmark as bench

    bench.test_repeated_indicator_reproduces_published_anchors(_subdir(run_dir, "ex56-a"))
    bench.test_repeated_indicator_reports_reliability_at_both_levels(_subdir(run_dir, "ex56-b"))


def _anchor_ex511(run_dir: Path) -> None:
    import test_structural_benchmark as bench

    bench.test_fit_indices_match_lavaan_reference(_subdir(run_dir, "ex511-a"))
    bench.test_structural_paths_match_published_estimates(_subdir(run_dir, "ex511-b"))
    bench.test_r_squared_reported_per_endogenous_construct(_subdir(run_dir, "ex511-c"))


def _anchor_ex316(run_dir: Path) -> None:
    import test_effects_benchmark as bench

    bench.test_point_estimates_match_published(_subdir(run_dir, "ex316-a"))
    bench.test_bootstrap_cis_within_tolerance_of_published(_subdir(run_dir, "ex316-b"))


def _anchor_close_fit(run_dir: Path) -> None:
    from burhan.stats.power import close_fit_power

    # Jobst, Bader & Moshagen (2021), PMC8367885: power 0.378 at df=15,
    # N=200, eps0=.05, epsA=.08, alpha=.05 (TC-09 certified pin).
    observed = close_fit_power(df=15, n=200)
    if round(observed, 3) != 0.378:
        raise AssertionError(f"close-fit anchor failed: {observed}")


ANCHORS: list[tuple[str, Callable[[Path], None]]] = [
    ("mplus-ex5.6", _anchor_ex56),
    ("mplus-ex5.11", _anchor_ex511),
    ("mplus-ex3.16", _anchor_ex316),
    ("maccallum-close-fit", _anchor_close_fit),
]


def _subdir(run_dir: Path, name: str) -> Path:
    path = run_dir / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def replicate_all(run_dir: Path) -> list[dict[str, Any]]:
    """Run every published anchor; any failure raises immediately."""
    results = []
    for name, anchor in ANCHORS:
        anchor(run_dir)
        results.append({"anchor": name, "status": "replicated"})
    return results


def parity_map_payload() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "authority": (
            "AT-M12-4 (FR-1502): certified by full replication of the published "
            "worked-example set; tolerances are the provenance-justified values "
            "from each anchor suite."
        ),
        "certified": dict(sorted(_CERTIFIED_SCOPES.items())),
        "non_parity": list(_NON_PARITY),
    }


def write_parity_map(path: Path) -> dict[str, Any]:
    payload = parity_map_payload()
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
