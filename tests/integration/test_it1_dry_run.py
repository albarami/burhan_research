"""IT-1 (AT-M15-1): the golden dry run.

A realistic study drives the full 13-stage DAG to ``COMPLETED`` under stubbed
nodes; the rendered ``METHOD_COMPLIANCE_CHECKLIST.md`` accounts for every
Stage-1A step PB-01..PB-19 (completed, except the two the study cannot enable —
PB-12 CMB and PB-14 respecification — which are flagged per the playbook), and
the Stage-1B stubs are recorded pass-through.
"""

from __future__ import annotations

from pathlib import Path

from it_util import build_certification
from orch_util import TickingClock

from burhan.core.orchestrator import Orchestrator


def test_golden_study_runs_end_to_end_to_completed(tmp_path: Path) -> None:
    cert = build_certification(tmp_path)
    result = Orchestrator(TickingClock()).run(
        cert.run_dir, cert.registry, manifest_fields=cert.manifest_fields
    )
    assert result.state == "COMPLETED"

    checklist = (cert.run_dir / "METHOD_COMPLIANCE_CHECKLIST.md").read_text(encoding="utf-8")
    # every Stage-1A step is accounted for (PB-01..PB-19), no step unaccounted
    for number in range(1, 20):
        assert f"PB-{number:02d}" in checklist
    # the two steps the study cannot enable are flagged, not silently completed
    for step in ("PB-12", "PB-14"):
        row = next(line for line in checklist.splitlines() if line.startswith(f"| {step} "))
        assert "flagged" in row

    # Stage-1B is pass-through: PB-20/PB-21 flagged and named in provenance
    provenance = (cert.run_dir / "PROVENANCE.jsonl").read_text(encoding="utf-8")
    for stage in ("narrate", "gate2", "package"):
        assert stage in provenance
    for step in ("PB-20", "PB-21"):
        row = next(line for line in checklist.splitlines() if line.startswith(f"| {step} "))
        assert "flagged" in row


def test_completed_stage_1a_steps_have_store_backed_evidence(tmp_path: Path) -> None:
    cert = build_certification(tmp_path)
    Orchestrator(TickingClock()).run(
        cert.run_dir, cert.registry, manifest_fields=cert.manifest_fields
    )
    # the results store carries at least one statistic per completed analytic family
    store = (cert.run_dir / "results" / "results.jsonl").read_text(encoding="utf-8")
    for family in (
        "power.n_to_q",
        "power.montecarlo",
        "prep.n_chain",
        "assumptions.estimator",
        "measurement.loadings",
        "structural.fit",
        "effects.total",
        "robustness.achieved_power",
    ):
        assert family in store, family
