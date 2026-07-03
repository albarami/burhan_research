"""Bounded gate retry loop (AT-M07-3/5; FR-303).

Reject → author revises on the exact fix-list → re-audit, bounded by
``policy.gates.max_retries``; exhaustion is ``GateExhausted`` (HALTED_GATE)
with the final verdict archived in the emitted halt report. A schema-invalid
verdict consumes a cycle — never a crash.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from review_util import approve_yaml, reject_yaml

from burhan.core.errors import GateExhausted, IntegrityHalt, reset_halt_sink, set_halt_sink
from burhan.core.policy import Policy
from burhan.review.node_c import Verdict, parse_verdict, run_gate

REPO = Path(__file__).resolve().parents[3]


class CapturingSink:
    def __init__(self) -> None:
        self.reports: list[dict] = []

    def emit(self, report: dict) -> None:
        self.reports.append(report)


@pytest.fixture
def sink() -> Iterator[CapturingSink]:
    capture = CapturingSink()
    set_halt_sink(capture)
    yield capture
    reset_halt_sink()


class StubAuthor:
    """Author-node stub: applies the fix-list, then produces a fixed artifact."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.audits = 0
        self.revisions: list[tuple[str, ...]] = []

    def audit(self) -> Verdict:
        response = self._responses[min(self.audits, len(self._responses) - 1)]
        self.audits += 1
        return parse_verdict(response)

    def revise(self, fixes: tuple[str, ...]) -> None:
        self.revisions.append(fixes)


def test_author_stub_fixes_on_fix_list_and_loop_approves() -> None:  # AT-M07-3
    author = StubAuthor([reject_yaml("name the dropped hypothesis H4b"), approve_yaml()])
    verdict = run_gate(gate="gate1", audit=author.audit, revise=author.revise, max_retries=2)
    assert verdict.verdict == "approve"
    assert author.audits == 2  # initial audit + one re-audit
    assert author.revisions == [("name the dropped hypothesis H4b",)]


def test_loop_terminates_within_max_retries_and_archives_final_verdict(
    sink: CapturingSink,
) -> None:  # AT-M07-3
    author = StubAuthor([reject_yaml("still wrong")])
    with pytest.raises(GateExhausted) as excinfo:
        run_gate(gate="gate1", audit=author.audit, revise=author.revise, max_retries=2)
    assert author.audits == 3  # initial + 2 bounded re-audits, then stop
    assert len(author.revisions) == 2
    assert excinfo.value.run_state == "HALTED_GATE"
    details = excinfo.value.to_report()["details"]
    assert details["gate"] == "gate1"
    assert details["cycles"] == 2
    assert details["final_verdict"]["verdict"] == "reject"
    assert details["final_verdict"]["fixes"] == ["still wrong"]
    # archived: the report reached the halt sink before propagation (standards §4)
    assert any(r["details"].get("gate") == "gate1" for r in sink.reports)


def test_retry_bound_comes_from_policy_gates_max_retries() -> None:  # FR-303
    policy = Policy.load(REPO / "policy" / "decision_policy.template.yaml", mode="certification")
    bound = policy.rule("gates.max_retries")
    assert bound == 2
    author = StubAuthor([reject_yaml("fix it")])
    with pytest.raises(GateExhausted):
        run_gate(gate="gate2", audit=author.audit, revise=author.revise, max_retries=bound)
    assert author.audits == bound + 1


def test_schema_invalid_verdict_counts_as_a_reject_cycle_not_a_crash() -> None:  # AT-M07-5
    author = StubAuthor(["Sure! Here's the verdict: {unbalanced: [", approve_yaml()])
    verdict = run_gate(gate="gate1", audit=author.audit, revise=author.revise, max_retries=2)
    assert verdict.verdict == "approve"
    assert len(author.revisions) == 1
    assert "verdict schema violation" in author.revisions[0][0]


def test_schema_invalid_forever_exhausts_as_halted_gate_not_a_crash() -> None:  # AT-M07-5
    author = StubAuthor(["- not\n- a\n- mapping\n"])
    with pytest.raises(GateExhausted) as excinfo:  # GateExhausted, never YAMLError
        run_gate(gate="gate2", audit=author.audit, revise=author.revise, max_retries=1)
    final = excinfo.value.to_report()["details"]["final_verdict"]
    assert final["schema_invalid"] is True


def test_whitespace_only_fix_consumes_a_retry_cycle() -> None:  # REJECT-TC07 fix 2
    author = StubAuthor(['verdict: reject\nfixes: [" "]\n', approve_yaml()])
    verdict = run_gate(gate="gate2", audit=author.audit, revise=author.revise, max_retries=2)
    assert verdict.verdict == "approve"
    assert len(author.revisions) == 1
    assert "verdict schema violation" in author.revisions[0][0]


def test_duplicate_mapping_keys_consume_a_retry_cycle() -> None:  # REJECT-TC07 fix 2
    # A duplicate verdict key must never collapse into a smuggled approve.
    author = StubAuthor(["verdict: reject\nverdict: approve\nfixes: []\n", approve_yaml()])
    verdict = run_gate(gate="gate1", audit=author.audit, revise=author.revise, max_retries=2)
    assert verdict.verdict == "approve"
    assert len(author.revisions) == 1
    assert "verdict schema violation" in author.revisions[0][0]


def test_non_positive_retry_bound_is_a_defect() -> None:
    author = StubAuthor([approve_yaml()])
    with pytest.raises(IntegrityHalt) as excinfo:
        run_gate(gate="gate1", audit=author.audit, revise=author.revise, max_retries=0)
    assert "max_retries" in excinfo.value.message
