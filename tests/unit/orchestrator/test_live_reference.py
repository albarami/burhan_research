"""TC-16 item 10 — the terminal-stage reference-comparison wrapper (fast, no DAG).

The live-only ``_PackageReferenceStage`` delegates to the real terminal stage,
then — before the seal — opens the completed run's results store, builds the
FR-1503 comparison, renders it, and writes ``REFERENCE_COMPARISON.md`` while
copying the reference-set bytes into the run tree. These assertions fail if the
delegation, the builder call, the render, the write, or the reference-byte copy
is removed. (Seal inclusion + rerun byte-identity are proven end-to-end in
``tests/integration/test_it7_live_run.py``.)
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, cast

import yaml

from burhan.cli.live import (
    REFERENCE_COMPARISON_FILENAME,
    _PackageReferenceStage,
    _record_reference,
)
from burhan.core.manifest import Manifest
from burhan.core.orchestrator import StageContext
from burhan.core.provenance import Provenance
from burhan.results.store import ResultsStore


class _Clock:
    def now(self) -> dt.datetime:
        return dt.datetime(2026, 7, 6, tzinfo=dt.UTC)


class _FakeTerminalStage:
    name = "package"
    consumes: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()

    def __init__(self) -> None:
        self.ran = False

    def execute(self, ctx: StageContext) -> None:
        self.ran = True


def _reference_set() -> dict[str, Any]:
    return {
        "study_id": "integration-adoption-2026",
        "source": {
            "description": "Fixture reference for the item-10 wrapper unit test.",
            "documents": [{"path": "inputs/manual.docx", "sha256": "a" * 64}],
            "caveats": "Fixture.",
        },
        "entries": [
            {
                "comparison_id": "REF-CFI",
                "domain": "fit",
                "metric": "cfi",
                "stat_id": "structural.fit.cfi",
                "reference_value": 0.95,
                "tolerance": 0.05,
            }
        ],
    }


def _ctx(run_dir: Path, store: ResultsStore, clock: _Clock) -> StageContext:
    # The wrapper and the fake terminal stage touch only run_dir/clock/(re-opened)
    # store, so manifest/provenance are unused stand-ins here.
    return StageContext(
        run_dir=run_dir,
        stage="package",
        stage_seed=0,
        master_seed=0,
        clock=clock,
        manifest=cast(Manifest, object()),
        provenance=cast(Provenance, object()),
        store=store,
    )


def test_wrapper_delegates_then_builds_renders_writes(tmp_path: Path) -> None:
    clock = _Clock()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    store = ResultsStore(run_dir / "results", clock)
    store.write(
        {
            "id": "structural.fit.cfi",
            "value": 0.962,
            "stage": "structural",
            "engine": "r_lavaan",
            "playbook_step": "PB-16",
        }
    )
    reference_path = tmp_path / "reference_set.yaml"
    reference_path.write_text(yaml.safe_dump(_reference_set(), sort_keys=True), encoding="utf-8")

    inner = _FakeTerminalStage()
    wrapper = _PackageReferenceStage(
        inner, _record_reference(reference_path), run_id="20260706T000000Z"
    )
    # Stage identity is delegated (Protocol conformance).
    assert (wrapper.name, wrapper.consumes, wrapper.produces) == ("package", (), ())

    wrapper.execute(_ctx(run_dir, store, clock))

    assert inner.ran  # the real terminal stage still runs (delegation)
    report = run_dir / REFERENCE_COMPARISON_FILENAME
    assert report.is_file()  # write
    text = report.read_text(encoding="utf-8")
    assert text.startswith("# Reference comparison")  # render
    assert "REF-CFI" in text  # builder processed the entry
    assert "0.962" in text  # builder resolved the store's burhan_value
    # reference-set bytes copied verbatim into the run tree (deterministic for rerun)
    copied = run_dir / "reference" / "reference_set.yaml"
    assert copied.read_bytes() == reference_path.read_bytes()
