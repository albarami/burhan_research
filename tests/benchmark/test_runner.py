"""AT-M12-4: the benchmark replication runner (FR-1502).

The runner replicates the published worked-example set end-to-end
(each anchor is the same pinned check its own suite certifies) and
writes the certified parity map; the committed map must match the
runner's output exactly, and the verification lane (AT-M12-2) must be
able to consume it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "src"))

import runner  # noqa: E402

from burhan.verify.parity import load_parity_map  # noqa: E402


def test_runner_replicates_published_set_and_writes_map(tmp_path: Path) -> None:
    results = runner.replicate_all(tmp_path)
    assert [entry["status"] for entry in results] == ["replicated"] * 4
    assert {entry["anchor"] for entry in results} == {
        "mplus-ex5.6",
        "mplus-ex5.11",
        "mplus-ex3.16",
        "maccallum-close-fit",
    }
    written = runner.write_parity_map(tmp_path / "parity_map.json")
    parsed = load_parity_map(written)
    assert "structural.paths" in parsed["certified"]
    assert parsed["certified"]["structural.paths"]["tolerance"] == 0.001
    assert "estimator.wlsmv" in parsed["non_parity"]


def test_committed_map_matches_runner_output(tmp_path: Path) -> None:
    # Drift detection: the committed certified map IS the runner's output.
    regenerated = tmp_path / "parity_map.json"
    runner.write_parity_map(regenerated)
    assert regenerated.read_text(encoding="utf-8") == runner.PARITY_MAP_PATH.read_text(
        encoding="utf-8"
    )


def test_committed_map_is_loadable_and_consumed_by_verification() -> None:
    data = json.loads(runner.PARITY_MAP_PATH.read_text(encoding="utf-8"))
    parsed = load_parity_map(data)
    # the scopes AT-M12-2's verification lane compares are certified
    assert {"structural.paths", "measurement.loadings", "measurement.reliability"} <= set(
        parsed["certified"]
    )
    for spec in parsed["certified"].values():
        assert spec["tolerance"] > 0
