"""Node A — study document → validated study contract (FR-201–206).

Subclasses the adapter base (closed allowlist: study document text and the
optional data dictionary — never raw data, FR-206). The versioned prompt
(prompts/node_a/v1.md) instructs YAML-only extraction of the instrument AS
DESIGNED (FR-202) with the AMBIGUOUS hard-stop protocol; this module then
enforces what the prompt asks for:

- an ``AMBIGUOUS:`` response is a hard failure carrying the model's stated
  reason — never a guess, never a silent default (FR-205);
- the response must parse as a YAML mapping and validate against the
  governed study_config schema, halting with the JSON path (FR-203);
- V1–V7 run over the model, with reverse-coding sources scanned
  deterministically from the document and dictionary (V7's single-source
  rule) and the dictionary cross-check authoritative for what it declares
  (FR-204).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

# Untyped third-party edge (no stubs in the locked dependency set).
import yaml  # type: ignore[import-untyped]

from burhan.contract.llm_base import AdapterBase, prompt_manifest_entry
from burhan.contract.validators import validate_contract
from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig
from burhan.core.errors import IntegrityHalt, halt


@dataclass(frozen=True)
class SourceDocumentRef:
    """One authoritative ``meta.source_documents`` entry (role, path, file digest)."""

    role: str
    path: str
    sha256: str


@dataclass(frozen=True)
class ContractProvenance:
    """Authoritative provenance/governance the ENGINE supplies for a Node A contract.

    ``meta.source_documents`` digests and ``methodology.playbook_id`` /
    ``playbook_version`` are schema-required but NOT derivable by an LLM reading a
    document — a fabricated file hash is forbidden (FR-206). The prompt instructs Node A
    to omit them; the live path resolves them from the actual input files and the
    governed playbook and injects them here, BEFORE schema validation, so
    ``validate_and_build`` sees a complete, authoritative contract.
    """

    source_documents: tuple[SourceDocumentRef, ...]
    playbook_id: str
    playbook_version: str


_AMBIGUOUS_MARKER = "AMBIGUOUS:"
_REVERSE_TOKEN = "reverse"
_NEGATED_REVERSE = re.compile(r"\bnot\s+reverse")


# Whole-response fence tags whose body is unwrapped before parsing; any other
# language tag is left in place to fail FR-203.
_YAML_FENCE_LANGS = frozenset({"", "yaml", "yml"})


def _strip_code_fence(text: str) -> str:
    """Unwrap a whole-response YAML markdown code fence if the model added one.

    Models sometimes wrap the YAML contract in a fenced code block. Only a fence
    tagged ``yaml``/``yml`` or a bare fence is unwrapped (its body is YAML); any
    other language tag is returned unchanged, to fail FR-203. Strips the opening
    fence line and a trailing fence line when present — the closing fence is
    absent when the response was truncated. Deterministic.
    """
    if not text.startswith("```"):
        return text
    first, _, rest = text.partition("\n")
    if first[3:].strip().lower() not in _YAML_FENCE_LANGS:
        return text  # non-YAML fence: leave it to fail FR-203
    lines = rest.splitlines()
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]  # drop the closing fence line (absent when truncated)
    return "\n".join(lines)


def default_template_path() -> Path:
    """The versioned Node A prompt (AD-04)."""
    return Path(__file__).resolve().parents[3] / "prompts" / "node_a" / "v1.md"


def _inject_provenance(raw: dict[str, Any], provenance: ContractProvenance) -> None:
    """Overwrite the non-LLM-derivable fields with the engine's authoritative values,
    in place, before schema validation.

    ``meta.source_documents`` and ``methodology.playbook_id``/``playbook_version`` are
    set to the engine's values regardless of what the model emitted (an LLM-supplied
    file hash is never trusted). If the model omitted the parent block entirely, the
    missing-required halt stands — the adapter never fabricates ``meta``/``methodology``.
    """
    meta = raw.get("meta")
    if isinstance(meta, dict):
        meta["source_documents"] = [
            {"role": sd.role, "path": sd.path, "sha256": sd.sha256}
            for sd in provenance.source_documents
        ]
    methodology = raw.get("methodology")
    if isinstance(methodology, dict):
        methodology["playbook_id"] = provenance.playbook_id
        methodology["playbook_version"] = provenance.playbook_version


class NodeA(AdapterBase):
    """The extraction node: documents in, validated study contract out."""

    node: ClassVar[str] = "node_a"
    ALLOWED_INPUTS: ClassVar[tuple[str, ...]] = ("study_document", "data_dictionary")

    def __init__(self, settings: Any, *, provider_call: Any, template_path: Path | None = None):
        super().__init__(settings, provider_call=provider_call)
        self._template_path = (
            template_path if template_path is not None else default_template_path()
        )
        self._template = self._template_path.read_text(encoding="utf-8")

    def prompt_manifest(self) -> dict[str, Any]:
        """Version + hash of the active prompt template for the manifest."""
        return prompt_manifest_entry(self._template_path)

    def extract(
        self,
        *,
        study_document: str,
        data_dictionary: str | None = None,
        export_path: Path | None = None,
        min_designed_items: int = 2,
        provenance: ContractProvenance | None = None,
    ) -> StudyConfig:
        """Extract, schema-validate, and cross-field-validate the contract.

        ``provenance`` (supplied on the live path) injects the engine's authoritative
        ``meta.source_documents`` and ``methodology.playbook_id``/``playbook_version``
        into the raw contract BEFORE schema validation — the adapter never authors those
        non-LLM-derivable fields (FR-206), and a fabricated file hash is never trusted.
        Without it the raw model output is validated as-is (a compliant response, which
        omits those fields, then halts typed on the missing required properties).
        """
        response = self.complete(study_document=study_document, data_dictionary=data_dictionary)
        stripped = response.strip()
        body = _strip_code_fence(stripped)  # unwrap a YAML fence before FR-205/FR-203 checks
        if body.startswith(_AMBIGUOUS_MARKER):
            halt(
                IntegrityHalt(
                    "extraction ambiguity is a hard failure, never a guess (FR-205)",
                    report={"reason": body},
                )
            )
        try:
            raw = yaml.safe_load(body)
        except yaml.YAMLError as exc:
            halt(
                IntegrityHalt(
                    "Node A output is not valid YAML (FR-203)",
                    report={"error": str(exc)},
                )
            )
        if not isinstance(raw, dict):
            halt(
                IntegrityHalt(
                    "Node A output is not a YAML mapping (FR-203)",
                    report={"type": type(raw).__name__},
                )
            )
        if provenance is not None:
            _inject_provenance(raw, provenance)
        config = validate_and_build(StudyConfig, raw)
        source_reversed = _scan_reversed_sources(
            [item.code for item in config.instrument.items],
            study_document,
            data_dictionary,
        )
        validate_contract(
            config,
            source_reversed=source_reversed,
            dictionary_text=data_dictionary,
            export_path=export_path,
            min_designed_items=min_designed_items,
        )
        return config

    def _build_prompt(self, inputs: dict[str, str | None]) -> str:
        return self._template.format(
            study_document=inputs.get("study_document") or "",
            data_dictionary=inputs.get("data_dictionary") or "(none provided)",
        )


def _scan_reversed_sources(
    item_codes: list[str], study_document: str, data_dictionary: str | None
) -> set[str]:
    """Deterministic reverse-coding evidence: lines naming an item + 'reverse'.

    This is the single-source rule's evidence base (V7): the contract may
    flag an item reverse-coded only if a source line says so. A line stating
    'not reverse…' is an explicit negative declaration — it is never positive
    evidence (the dictionary cross-check owns negative-vs-contract conflicts).
    """
    reversed_items: set[str] = set()
    source_text = study_document + "\n" + (data_dictionary or "")
    for line in source_text.splitlines():
        lowered = line.lower()
        if _REVERSE_TOKEN not in lowered:
            continue
        if _NEGATED_REVERSE.search(lowered):
            continue
        for code in item_codes:
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(code)}(?![A-Za-z0-9_])", line):
                reversed_items.add(code)
    return reversed_items
