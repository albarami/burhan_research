"""Method Advisory emission (FR-1203, FR-403; Concept §10.2).

When accumulated evidence challenges a protected decision, the system runs
to the boundary of what remains defensible and emits ``METHOD_ADVISORY.md``
— diagnostics, recommendation, citations, impact — then raises
:class:`AdvisoryStop` (run state ``COMPLETED_TO_BOUNDARY``). The orchestrator
(TC-04) catches the stop and completes the defensible-scope package; until
then the raise IS the wiring stub. The advisory and its provenance entry are
the record a viva panel reads (Concept §10.2).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, NoReturn

from burhan.core.artifacts.canonical import check_payload, dumps, sha256_file
from burhan.core.artifacts.clock import Clock
from burhan.core.artifacts.models import format_utc_seconds
from burhan.core.errors import AdvisoryStop, IntegrityHalt, halt_with_file
from burhan.core.provenance import Provenance

ADVISORY_FILENAME = "METHOD_ADVISORY.md"

_MANDATED_SECTIONS = ("Diagnostics", "Recommendation", "Citations", "Impact")


class Advisory:
    """Writer of the one-per-run Method Advisory."""

    def __init__(self, directory: Path, provenance: Provenance, clock: Clock) -> None:
        self._directory = directory
        self._provenance = provenance
        self._clock = clock

    def emit(
        self,
        *,
        stage: str,
        trigger: str,
        diagnostics: dict[str, Any],
        recommendation: str,
        citations: list[str],
        impact: str,
    ) -> NoReturn:
        """Write METHOD_ADVISORY.md + provenance entry, then AdvisoryStop.

        All four mandated elements (FR-1203: diagnostics, recommendation,
        citations, impact) must be non-empty and canonical-serializable.
        Exactly one advisory may exist per run.
        """
        if not (diagnostics and recommendation and citations and impact and trigger):
            halt_with_file(
                IntegrityHalt(
                    "FR-1203 requires diagnostics, recommendation, citations, and "
                    "impact — all non-empty",
                    report={
                        "empty": [
                            name
                            for name, value in (
                                ("trigger", trigger),
                                ("diagnostics", diagnostics),
                                ("recommendation", recommendation),
                                ("citations", citations),
                                ("impact", impact),
                            )
                            if not value
                        ]
                    },
                ),
                self._directory,
            )
        check_payload({"diagnostics": diagnostics, "citations": citations})
        path = self._directory / ADVISORY_FILENAME
        if path.exists():
            halt_with_file(
                IntegrityHalt(
                    "METHOD_ADVISORY.md already exists; one advisory per run",
                    report={"path": str(path)},
                ),
                self._directory,
            )
        try:
            stamp = format_utc_seconds(self._clock.now())
        except ValueError as exc:  # typed taxonomy, never a raw ValueError
            halt_with_file(
                IntegrityHalt(
                    "injected clock produced a non-canonical timestamp",
                    report={"error": str(exc)},
                ),
                self._directory,
            )
        self._directory.mkdir(parents=True, exist_ok=True)
        path.write_text(
            self._render(
                stage=stage,
                trigger=trigger,
                diagnostics=diagnostics,
                recommendation=recommendation,
                citations=citations,
                impact=impact,
                stamp=stamp,
            ),
            encoding="utf-8",
        )
        self._provenance.append(
            {
                "stage": stage,
                "actor": "policy",
                "event_type": "advisory_issued",
                "trigger": trigger,
                "effect": "METHOD_ADVISORY.md emitted; run proceeds to defensible boundary",
                "artifact_refs": [{"path": ADVISORY_FILENAME, "sha256": sha256_file(path)}],
                "details": {"citations": citations, "impact": impact},
            }
        )
        halt_with_file(
            AdvisoryStop(
                "method advisory issued; completing to the defensible boundary (FR-1203)",
                report={
                    "stage": stage,
                    "trigger": trigger,
                    "advisory": ADVISORY_FILENAME,
                    "recommendation": recommendation,
                },
            ),
            self._directory,
        )

    @staticmethod
    def _render(
        *,
        stage: str,
        trigger: str,
        diagnostics: dict[str, Any],
        recommendation: str,
        citations: list[str],
        impact: str,
        stamp: str,
    ) -> str:
        lines = [
            "# METHOD_ADVISORY",
            "",
            f"- stage: {stage}",
            f"- ts: {stamp}",
            f"- trigger: {trigger}",
            "",
            f"## {_MANDATED_SECTIONS[0]}",
            "",
        ]
        for key in sorted(diagnostics):
            lines.append(f"- {key}: {dumps(diagnostics[key])}")
        lines += ["", f"## {_MANDATED_SECTIONS[1]}", "", recommendation, ""]
        lines += [f"## {_MANDATED_SECTIONS[2]}", ""]
        lines += [f"- {citation}" for citation in citations]
        lines += ["", f"## {_MANDATED_SECTIONS[3]}", "", impact, ""]
        return "\n".join(lines)
