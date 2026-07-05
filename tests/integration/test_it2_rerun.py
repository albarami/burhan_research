"""IT-2 (AT-M15-2): rerun identity.

``rerun`` re-executes the sealed IT-1 run in full and asserts every regenerated
artifact is byte-identical (NFR-101); a stub that is not reproducible is caught
by that same assertion.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from it_util import build_certification
from orch_util import StubStage, TickingClock, manifest_fields, stub_registry

from burhan.core.errors import VerificationHalt
from burhan.core.orchestrator import Orchestrator


def test_real_pipeline_reruns_byte_identical(tmp_path: Path) -> None:
    cert = build_certification(tmp_path)
    Orchestrator(TickingClock()).run(
        cert.run_dir, cert.registry, manifest_fields=cert.manifest_fields
    )
    target = tmp_path / "rerun"
    # rerun re-executes fully and raises VerificationHalt on any byte difference;
    # returning COMPLETED is the identity guarantee.
    result = Orchestrator(TickingClock()).rerun(cert.run_dir, cert.registry, target_run_dir=target)
    assert result.state == "COMPLETED"


def test_identity_assertion_catches_a_nondeterministic_stub(tmp_path: Path) -> None:
    source = tmp_path / "source"
    fields = dict(manifest_fields())
    Orchestrator(TickingClock()).run(source, stub_registry(), manifest_fields=fields)
    # a stub that regenerates different bytes (a planted nondeterminism) must not
    # slip past the rerun identity assertion.
    tampered = stub_registry(
        {
            "gate2": StubStage(
                "gate2",
                action=lambda ctx: (ctx.run_dir / "gate2.txt").write_text(
                    "not reproducible", encoding="utf-8"
                ),
            )
        }
    )
    with pytest.raises(VerificationHalt):
        Orchestrator(TickingClock()).rerun(source, tampered, target_run_dir=tmp_path / "rerun")
