"""Method Advisory tests (AT-M02-5; FR-1203, FR-403).

``Advisory.emit`` writes a section-conformant METHOD_ADVISORY.md, appends an
``advisory_issued`` provenance entry referencing the file by hash, and raises
``AdvisoryStop`` — the COMPLETED_TO_BOUNDARY path (orchestrator wiring lands
with TC-04).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from gov_util import FixedClock

from burhan.core.advisory import ADVISORY_FILENAME, Advisory
from burhan.core.artifacts.canonical import sha256_file
from burhan.core.errors import AdvisoryStop, IntegrityHalt, set_halt_sink
from burhan.core.provenance import Provenance


class CapturingSink:
    def __init__(self) -> None:
        self.reports: list[dict[str, Any]] = []

    def emit(self, report: dict[str, Any]) -> None:
        self.reports.append(report)


@pytest.fixture(autouse=True)
def _sink() -> Any:
    from burhan.core.errors import reset_halt_sink

    sink = CapturingSink()
    set_halt_sink(sink)
    yield sink
    reset_halt_sink()


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    return tmp_path / "run"


@pytest.fixture
def advisory(run_dir: Path) -> Advisory:
    provenance = Provenance(run_dir / "PROVENANCE.jsonl", FixedClock())
    return Advisory(run_dir, provenance, FixedClock())


def _payload() -> dict[str, Any]:
    return {
        "stage": "power",
        "trigger": "N:q below playbook floor",
        "diagnostics": {"n": 96, "free_parameters": 58, "n_q_ratio": 1.66},
        "recommendation": (
            "Consider PLS-SEM or additional data collection before structural claims."
        ),
        "citations": ["Kline (2016)", "Hair et al. (2019)"],
        "impact": (
            "Structural estimates would be underpowered; measurement stage stays defensible."
        ),
    }


def test_emit_writes_conformant_advisory_and_raises_boundary_stop(
    advisory: Advisory, run_dir: Path, _sink: CapturingSink
) -> None:  # AT-M02-5
    with pytest.raises(AdvisoryStop) as excinfo:
        advisory.emit(**_payload())
    assert excinfo.value.run_state == "COMPLETED_TO_BOUNDARY"

    content = (run_dir / ADVISORY_FILENAME).read_text(encoding="utf-8")
    for section in (
        "# METHOD_ADVISORY",
        "## Diagnostics",
        "## Recommendation",
        "## Citations",
        "## Impact",
    ):
        assert section in content
    assert "n_q_ratio" in content and "1.66" in content  # diagnostics rendered
    assert "Kline (2016)" in content
    assert "underpowered" in content

    # sink received the machine-readable report before propagation
    assert any(r["run_state"] == "COMPLETED_TO_BOUNDARY" for r in _sink.reports)


def test_emit_appends_provenance_entry_with_artifact_hash(
    advisory: Advisory, run_dir: Path
) -> None:  # AT-M02-5
    with pytest.raises(AdvisoryStop):
        advisory.emit(**_payload())
    line = json.loads((run_dir / "PROVENANCE.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert line["event_type"] == "advisory_issued"
    assert line["actor"] == "policy"
    assert line["stage"] == "power"
    ref = line["artifact_refs"][0]
    assert ref["path"] == ADVISORY_FILENAME
    assert ref["sha256"] == sha256_file(run_dir / ADVISORY_FILENAME)


def test_emit_is_write_once(advisory: Advisory) -> None:
    with pytest.raises(AdvisoryStop):
        advisory.emit(**_payload())
    with pytest.raises(IntegrityHalt):
        advisory.emit(**_payload())  # a second advisory is a defect


@pytest.mark.parametrize("missing", ["diagnostics", "recommendation", "citations", "impact"])
def test_emit_requires_all_mandated_elements(advisory: Advisory, missing: str) -> None:
    payload = _payload()
    payload[missing] = {} if missing == "diagnostics" else type(payload[missing])()
    with pytest.raises(IntegrityHalt):
        advisory.emit(**payload)


def test_emit_rejects_non_canonical_diagnostics(advisory: Advisory) -> None:
    payload = _payload()
    payload["diagnostics"] = {"bad": object()}
    with pytest.raises(IntegrityHalt):
        advisory.emit(**payload)


def test_halt_report_colocated_on_boundary_stop(advisory: Advisory, run_dir: Path) -> None:
    from burhan.core.errors import HALT_REPORT_FILENAME

    with pytest.raises(AdvisoryStop):
        advisory.emit(**_payload())
    report = json.loads((run_dir / HALT_REPORT_FILENAME).read_text(encoding="utf-8"))
    assert report["halt_class"] == "AdvisoryStop"
