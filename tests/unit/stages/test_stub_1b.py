"""TC-15 Task 3 / AT-M15-6: the Stage-1B certification pass-through stubs.

narrate (S9), gate2 (G2), and package (S10) are wired as deterministic
pass-throughs: they advance the state machine and emit placeholder
artifacts, narrate/package mark their playbook step (PB-20/PB-21) as
``flagged`` pass-through (D1 ruling), and the package stub renders the
compliance checklist once every step is recorded. The stub module carries
no narration/checker/reporting logic — that stays with TC-13/TC-14
(AT-M15-6, asserted by source inspection).
"""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

from stages_util import playbook, stage_context

from burhan.core.compliance import Compliance
from burhan.stages import stub_1b
from burhan.stages.stub_1b import StubGate2, StubNarrate, StubPackage

COMPLIANCE_JOURNAL = "compliance_journal.jsonl"


def _journal_rows(run_dir: Path) -> list[dict[str, str]]:
    path = run_dir / COMPLIANCE_JOURNAL
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_stub_stage_names_match_stage_1b_dag_slots() -> None:
    assert StubNarrate(playbook=playbook()).name == "narrate"
    assert StubGate2().name == "gate2"
    assert StubPackage(playbook=playbook()).name == "package"


def test_narrate_stub_marks_pb20_flagged_and_writes_placeholder(tmp_path: Path) -> None:
    ctx = stage_context(tmp_path, stage="narrate")
    StubNarrate(playbook=playbook()).execute(ctx)
    rows = {r["step_id"]: r for r in _journal_rows(tmp_path)}
    assert rows["PB-20"]["status"] == "flagged"
    assert "pass-through" in rows["PB-20"]["evidence"].lower()
    assert any(tmp_path.rglob("*.md")) or any(tmp_path.rglob("*.json"))  # a placeholder artifact


def test_gate2_stub_passes_through_without_a_playbook_step(tmp_path: Path) -> None:
    ctx = stage_context(tmp_path, stage="gate2")
    StubGate2().execute(ctx)  # must not raise; gate2 has no PB step
    assert all(r["step_id"] != "gate2" for r in _journal_rows(tmp_path))


def test_package_stub_marks_pb21_and_renders_full_checklist(tmp_path: Path) -> None:
    ctx = stage_context(tmp_path, stage="package")
    pb = playbook()
    # Pre-mark PB-01..PB-20 (as a full pipeline would) so the package stub's
    # render sees every step recorded.
    journal = tmp_path / COMPLIANCE_JOURNAL
    pre = Compliance(pb, ctx.store, journal, ctx.clock)
    for step in pb.step_ids:
        if step != "PB-21":
            pre.mark(step, "flagged", "pre-marked for the render test")
    StubPackage(playbook=pb).execute(ctx)
    rows = {r["step_id"]: r for r in _journal_rows(tmp_path)}
    assert rows["PB-21"]["status"] == "flagged"
    checklist = tmp_path / "METHOD_COMPLIANCE_CHECKLIST.md"
    assert checklist.exists()
    text = checklist.read_text(encoding="utf-8")
    for step in pb.step_ids:
        assert step in text  # all 21 steps rendered


def test_stub_module_has_no_stage_1b_reporting_logic() -> None:  # AT-M15-6
    source = Path(inspect.getsourcefile(stub_1b)).read_text(encoding="utf-8")  # type: ignore[arg-type]
    lowered = source.lower()
    # No real narration / number-resolution checker / reporting / office packs.
    for token in (
        "number_resolution",
        "claim_check",
        "apa",
        "spss",
        "amos",
        "render_findings",
        "narrative_text",
    ):
        assert token not in lowered, f"stub leaked Stage-1B logic token: {token}"
    # No imports of (future) real narrate/package/checker modules.
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith("burhan.narrate")
            assert not node.module.startswith("burhan.package")
            assert "checker" not in node.module
