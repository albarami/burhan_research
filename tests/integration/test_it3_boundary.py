"""IT-3 (AT-M15-3): the advisory boundary.

An under-powered study trips the N:q floor at the power gate, which emits a
Method Advisory; the orchestrator maps that to ``COMPLETED_TO_BOUNDARY`` and
seals a defensible-scope package up to the advisory. No R fit runs — the
advisory fires before the Monte-Carlo step.
"""

from __future__ import annotations

from pathlib import Path

from it_util import build_certification
from orch_util import TickingClock

from burhan.core.orchestrator import Orchestrator


def test_underpowered_study_stops_at_the_advisory_boundary(tmp_path: Path) -> None:
    # N:q = 100 / 26 = 3.85, below the 5:1 floor -> Method Advisory at PB-01.
    cert = build_certification(tmp_path, n=100)
    result = Orchestrator(TickingClock()).run(
        cert.run_dir, cert.registry, manifest_fields=cert.manifest_fields
    )
    assert result.state == "COMPLETED_TO_BOUNDARY"
    assert (cert.run_dir / "METHOD_ADVISORY.md").exists()
    # the tail stages never ran: no structural statistics were written.
    results = cert.run_dir / "results" / "results.jsonl"
    assert not results.exists() or "structural.fit" not in results.read_text(encoding="utf-8")
