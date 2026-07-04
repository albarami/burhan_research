"""Stage-1B certification pass-through stubs (TC-15).

narrate (S9), gate2 (G2), and package (S10) exist only to let a golden
study traverse the full 13-stage DAG to ``COMPLETED`` during certification.
Each satisfies the ``Stage`` protocol, advances the state machine, and
writes a deterministic placeholder artifact. narrate and package mark their
playbook step (PB-20 / PB-21) as ``flagged`` pass-through (D1 ruling — the
work is deferred, not completed); the package stub renders the compliance
checklist once every step is recorded.

This module contains **no** narration, number-resolution checker, or
reporting/office-pack logic — that behavior belongs to TC-13 (narrate) and
TC-14 (package). The boundary is asserted by AT-M15-6.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from burhan.stages.context import COMPLIANCE_CHECKLIST, compliance, write_artifact

if TYPE_CHECKING:
    from burhan.core.orchestrator import StageContext
    from burhan.core.playbook import Playbook

_PASS_THROUGH = "certification pass-through stub (TC-15); real behavior deferred to TC-13/TC-14"


class StubNarrate:
    """S9 narrate pass-through: placeholder draft + PB-20 flagged."""

    name = "narrate"
    consumes: tuple[str, ...] = ("stats/structural.json", "stats/effects.json")
    produces: tuple[str, ...] = ("narrate/DRAFT_PLACEHOLDER.json",)

    def __init__(self, *, playbook: Playbook) -> None:
        self._playbook = playbook

    def execute(self, ctx: StageContext) -> None:
        write_artifact(
            ctx,
            "narrate/DRAFT_PLACEHOLDER.json",
            {"stage": "narrate", "status": "pass_through", "note": _PASS_THROUGH},
        )
        compliance(ctx, self._playbook).mark("PB-20", "flagged", _PASS_THROUGH)


class StubGate2:
    """G2 findings-gate pass-through: placeholder approve, no playbook step."""

    name = "gate2"
    consumes: tuple[str, ...] = ("narrate/DRAFT_PLACEHOLDER.json",)
    produces: tuple[str, ...] = ("gate2/VERDICT_PLACEHOLDER.json",)

    def execute(self, ctx: StageContext) -> None:
        write_artifact(
            ctx,
            "gate2/VERDICT_PLACEHOLDER.json",
            {"stage": "gate2", "verdict": "pass_through", "note": _PASS_THROUGH},
        )


class StubPackage:
    """S10 package pass-through: PB-21 flagged, then render the checklist."""

    name = "package"
    consumes: tuple[str, ...] = ("gate2/VERDICT_PLACEHOLDER.json",)
    produces: tuple[str, ...] = (COMPLIANCE_CHECKLIST, "package/PACKAGE_PLACEHOLDER.json")

    def __init__(self, *, playbook: Playbook) -> None:
        self._playbook = playbook

    def execute(self, ctx: StageContext) -> None:
        tracker = compliance(ctx, self._playbook)
        tracker.mark("PB-21", "flagged", _PASS_THROUGH)
        # Every step is now recorded (Stage-1A completed, Stage-1B flagged):
        # render the method-compliance checklist as the packaged evidence.
        checklist = tracker.render()
        (ctx.run_dir / COMPLIANCE_CHECKLIST).write_text(checklist, encoding="utf-8")
        write_artifact(
            ctx,
            "package/PACKAGE_PLACEHOLDER.json",
            {"stage": "package", "status": "pass_through", "note": _PASS_THROUGH},
        )
