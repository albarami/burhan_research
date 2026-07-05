"""Shared helpers for the TC-15 stage-adapter unit tests.

Builds a real ``StageContext`` (manifest + provenance + results store) over a
tmp run dir, and loads the governed playbook in certification mode (the mode
TC-15/M5 runs use while the playbook is draft).
"""

from __future__ import annotations

from pathlib import Path

from orch_util import TickingClock, manifest_fields

from burhan.core.artifacts import seeds
from burhan.core.artifacts.clock import Clock
from burhan.core.manifest import Manifest
from burhan.core.orchestrator import StageContext
from burhan.core.playbook import Playbook
from burhan.core.provenance import Provenance
from burhan.results.store import ResultsStore

REPO = Path(__file__).resolve().parents[3]


def playbook() -> Playbook:
    return Playbook.load(REPO / "playbooks" / "CB_SEM_PLAYBOOK_v1.0.yaml", mode="certification")


def stage_context(run_dir: Path, *, stage: str, clock: Clock | None = None) -> StageContext:
    the_clock: Clock = clock if clock is not None else TickingClock()
    fields = manifest_fields()
    master = int(fields["master_seed"])
    manifest = Manifest.open(run_dir, the_clock, fields)
    provenance = Provenance(run_dir / "PROVENANCE.jsonl", the_clock)
    store = ResultsStore(run_dir / "results", the_clock)
    return StageContext(
        run_dir=run_dir,
        stage=stage,
        stage_seed=seeds.derive(master, stage, 0),
        master_seed=master,
        clock=the_clock,
        manifest=manifest,
        provenance=provenance,
        store=store,
    )
