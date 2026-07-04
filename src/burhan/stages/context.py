"""Shared helpers for the TC-15 stage adapters.

Everything the adapters need beyond the certified module calls: the
run-wide compliance journal, provenance recording of a written artifact,
and (Task 4) governance materialization + store-row hygiene. Kept here so
each adapter stays thin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from burhan.core.artifacts.canonical import dumps
from burhan.core.artifacts.models import ProvenanceActor, ProvenanceEventType
from burhan.core.compliance import Compliance

if TYPE_CHECKING:
    from pathlib import Path

    from burhan.core.orchestrator import StageContext
    from burhan.core.playbook import Playbook

# The run-wide compliance journal (append-only marks; one row per playbook
# step) and the rendered checklist the package stage emits from it.
COMPLIANCE_JOURNAL = "compliance_journal.jsonl"
COMPLIANCE_CHECKLIST = "METHOD_COMPLIANCE_CHECKLIST.md"


def compliance(ctx: StageContext, playbook: Playbook) -> Compliance:
    """Open the run-wide compliance tracker (replays prior stages' marks)."""
    return Compliance(playbook, ctx.store, ctx.run_dir / COMPLIANCE_JOURNAL, ctx.clock)


def write_artifact(ctx: StageContext, relative: str, payload: object) -> Path:
    """Write a canonical-JSON artifact under the run dir and record it.

    Deterministic (canonical writer, injected clock); appends an
    ``artifact_written`` provenance entry naming the stage and path.
    """
    path = ctx.run_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(payload) + "\n", encoding="utf-8")
    ctx.provenance.append(
        {
            "stage": ctx.stage,
            "actor": ProvenanceActor.WORKER.value,
            "event_type": ProvenanceEventType.ARTIFACT_WRITTEN.value,
            "trigger": f"{ctx.stage} produced an artifact",
            "effect": f"wrote {relative}",
        }
    )
    return path
