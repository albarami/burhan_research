"""Node C — the Muḥāsaba reviewer: Gate 1 and Gate 2 audits (FR-301–305).

Review-only by construction (FR-305): this module exposes two audit doors
and the prompt manifest — no artifact writes, no compute API, no paths out.
Both gates subclass the adapter base (closed allowlists; raw data halts at
the boundary; lineage independence from Node A enforced at settings load,
FR-304).

The verdict contract is strict and closed (FR-303): ``verdict: approve``
with no fixes, or ``verdict: reject`` with exact fixes. A model response
violating the schema is a *pseudo-reject* — it consumes a retry cycle in
:func:`run_gate`, never a crash (AT-M07-5). Exhausting the policy bound
(``gates.max_retries``) halts as :class:`GateExhausted` (HALTED_GATE) with
the final verdict archived in the emitted report.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Literal

# Untyped third-party edge (no stubs in the locked dependency set).
import yaml  # type: ignore[import-untyped]

from burhan.contract.llm_base import AdapterBase, prompt_manifest_entry
from burhan.core.errors import GateExhausted, IntegrityHalt, halt

_VERDICT_KEYS = frozenset({"verdict", "fixes"})


def default_template_dir() -> Path:
    """The versioned Node C prompt directory (AD-04)."""
    return Path(__file__).resolve().parents[3] / "prompts" / "node_c"


@dataclass(frozen=True)
class Verdict:
    """A schema-bound gate verdict: approve, or reject with exact fixes."""

    verdict: Literal["approve", "reject"]
    fixes: tuple[str, ...]
    schema_invalid: bool = False

    def to_report(self) -> dict[str, Any]:
        """Archive form for halt reports and the manifest."""
        return {
            "verdict": self.verdict,
            "fixes": list(self.fixes),
            "schema_invalid": self.schema_invalid,
        }


def _schema_violation(reason: str) -> Verdict:
    return Verdict(
        verdict="reject",
        fixes=(f"verdict schema violation: {reason}",),
        schema_invalid=True,
    )


def parse_verdict(response: str) -> Verdict:
    """Parse a model response against the closed verdict schema (FR-303).

    The schema is exactly two keys — ``verdict: approve|reject`` and
    ``fixes`` (a list of non-empty strings, non-empty iff reject). Any
    violation returns a pseudo-reject marked ``schema_invalid`` so the
    retry loop counts it as a reject cycle rather than crashing
    (AT-M07-5; architecture §5: outputs failing schema validation count
    as rejects).
    """
    try:
        raw = yaml.safe_load(response)
    except yaml.YAMLError as exc:
        return _schema_violation(f"not valid YAML: {exc}")
    if not isinstance(raw, dict):
        return _schema_violation(f"not a mapping: {type(raw).__name__}")
    if set(raw) != _VERDICT_KEYS:
        return _schema_violation("keys must be exactly verdict, fixes")
    if raw["verdict"] not in ("approve", "reject"):
        return _schema_violation("verdict must be approve or reject")
    fixes = raw["fixes"]
    if not isinstance(fixes, list) or not all(isinstance(fix, str) and fix for fix in fixes):
        return _schema_violation("fixes must be a list of non-empty strings")
    if raw["verdict"] == "approve" and fixes:
        return _schema_violation("approve must not carry fixes")
    if raw["verdict"] == "reject" and not fixes:
        return _schema_violation("reject must carry exact fixes (FR-303)")
    return Verdict(verdict=raw["verdict"], fixes=tuple(fixes))


def _load_template(template_path: Path) -> str:
    if not template_path.is_file():
        halt(
            IntegrityHalt(
                "prompt template missing",
                report={"path": str(template_path)},
            )
        )
    return template_path.read_text(encoding="utf-8")


class _Gate1Adapter(AdapterBase):
    """Gate 1: the study contract against its source artifacts (FR-301)."""

    node: ClassVar[str] = "node_c"
    ALLOWED_INPUTS: ClassVar[tuple[str, ...]] = (
        "study_contract",
        "study_document",
        "data_dictionary",
    )

    def __init__(
        self, settings: Any, *, provider_call: Callable[[str], str], template_path: Path
    ) -> None:
        super().__init__(settings, provider_call=provider_call)
        self._template = _load_template(template_path)

    def _build_prompt(self, inputs: dict[str, str | None]) -> str:
        return self._template.format(
            study_contract=inputs.get("study_contract") or "",
            study_document=inputs.get("study_document") or "",
            data_dictionary=inputs.get("data_dictionary") or "(none provided)",
        )


class _Gate2Adapter(AdapterBase):
    """Gate 2: the findings draft against store + decision log (FR-302)."""

    node: ClassVar[str] = "node_c"
    ALLOWED_INPUTS: ClassVar[tuple[str, ...]] = (
        "findings_draft",
        "results_store",
        "decision_log",
    )

    def __init__(
        self, settings: Any, *, provider_call: Callable[[str], str], template_path: Path
    ) -> None:
        super().__init__(settings, provider_call=provider_call)
        self._template = _load_template(template_path)

    def _build_prompt(self, inputs: dict[str, str | None]) -> str:
        return self._template.format(
            findings_draft=inputs.get("findings_draft") or "",
            results_store=inputs.get("results_store") or "",
            decision_log=inputs.get("decision_log") or "",
        )


class NodeC:
    """The Muḥāsaba reviewer: two audit doors, review-only (FR-305)."""

    def __init__(
        self,
        settings: Any,
        *,
        provider_call: Callable[[str], str],
        template_dir: Path | None = None,
    ) -> None:
        directory = template_dir if template_dir is not None else default_template_dir()
        self._gate1_template = directory / "v1_gate1.md"
        self._gate2_template = directory / "v1_gate2.md"
        self._gate1 = _Gate1Adapter(
            settings, provider_call=provider_call, template_path=self._gate1_template
        )
        self._gate2 = _Gate2Adapter(
            settings, provider_call=provider_call, template_path=self._gate2_template
        )

    def gate1(
        self,
        *,
        study_contract: str,
        study_document: str,
        data_dictionary: str | None = None,
    ) -> Verdict:
        """Audit the study contract against its sources (FR-301)."""
        return parse_verdict(
            self._gate1.complete(
                study_contract=study_contract,
                study_document=study_document,
                data_dictionary=data_dictionary,
            )
        )

    def gate2(self, *, findings_draft: str, results_store: str, decision_log: str) -> Verdict:
        """Audit the findings draft against store + decision log (FR-302)."""
        return parse_verdict(
            self._gate2.complete(
                findings_draft=findings_draft,
                results_store=results_store,
                decision_log=decision_log,
            )
        )

    def prompt_manifest(self) -> list[dict[str, Any]]:
        """Version + hash of both gate templates for the run manifest (AD-04)."""
        return [
            prompt_manifest_entry(self._gate1_template),
            prompt_manifest_entry(self._gate2_template),
        ]


def run_gate(
    *,
    gate: str,
    audit: Callable[[], Verdict],
    revise: Callable[[tuple[str, ...]], None],
    max_retries: int,
) -> Verdict:
    """Bounded reject → revise → re-audit loop (FR-303).

    ``max_retries`` — the policy rule ``gates.max_retries`` — bounds the
    revise cycles after the initial audit. Each reject hands the author
    node the exact fix-list; exhaustion halts as :class:`GateExhausted`
    (HALTED_GATE) with the final verdict archived in the emitted report
    (standards §4: report written before propagation).
    """
    if max_retries < 1:
        halt(
            IntegrityHalt(
                "gates.max_retries must be a positive bound (FR-303)",
                report={"gate": gate, "max_retries": max_retries},
            )
        )
    verdict = audit()
    cycles = 0
    while verdict.verdict != "approve":
        if cycles == max_retries:
            halt(
                GateExhausted(
                    "gate retries exhausted (FR-303): stopping with the final verdict",
                    report={
                        "gate": gate,
                        "cycles": cycles,
                        "final_verdict": verdict.to_report(),
                    },
                )
            )
        revise(verdict.fixes)
        cycles += 1
        verdict = audit()
    return verdict
