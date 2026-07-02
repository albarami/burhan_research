"""Decision policy engine: loader, rule evaluator, decision logger (FR-1201).

The policy is the researcher-authored operational rulebook (Concept §10.1).
Loading validates against ``policy/decision_policy.schema.yaml`` plus the
loader cross-checks the schema documents:

- **D1** — ``meta.status: approved`` is required for production-mode loads;
  certification mode may load drafts.
- **D2** — every playbook ``policy_ref`` (and ``preauthorization_policy_ref``)
  must resolve to an addressable path in the policy document
  (:meth:`Policy.verify_playbook_refs`).
- **D3** — ``measurement.item_deletion.preauthorized_rules`` may be present
  only when ``preauthorized`` is true.

Every operational judgment resolves through :meth:`Policy.decide`, which
writes a :class:`DecisionEntry` citing the rule id and policy version to the
append-only decision log; ``DECISION_LOG.md`` is rendered from that JSONL and
adds nothing the entries do not contain (decision_log.schema.json).
"""

from __future__ import annotations

import copy
import json
import threading
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from typing import Any, Literal, NoReturn, cast

# Untyped third-party edges (no stubs in the locked dependency set).
import yaml  # type: ignore[import-untyped]
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import best_match  # type: ignore[import-untyped]

from burhan.core.artifacts.canonical import check_payload, dumps, sha256_file
from burhan.core.artifacts.clock import Clock
from burhan.core.artifacts.loader import dump_canonical, validate_and_build
from burhan.core.artifacts.models import DecisionEntry, format_utc_seconds
from burhan.core.errors import BurhanHalt, IntegrityHalt, halt, halt_with_file, write_halt_report

Mode = Literal["production", "certification"]

POLICY_SCHEMA_FILENAME = "decision_policy.schema.yaml"
REGISTRY_SCHEMA_FILENAME = "protected_registry.schema.yaml"

_LOG_OWNED_FIELDS = ("schema_version", "seq", "ts")


def governance_dir() -> Path:
    """Location of the governed policy/registry contracts (repo ``policy/``)."""
    return Path(__file__).resolve().parents[3] / "policy"


@cache
def governance_validator(schema_filename: str) -> Draft202012Validator:
    """Cached draft-2020-12 validator for a governance schema file."""
    schema = yaml.safe_load((governance_dir() / schema_filename).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def check_governance_instance(schema_filename: str, instance: object) -> None:
    """Validate against a governance schema; halt with the JSON path."""
    error = best_match(governance_validator(schema_filename).iter_errors(instance))
    if error is not None:
        halt(
            IntegrityHalt(
                f"schema violation [{schema_filename}] at {error.json_path}: {error.message}",
                report={
                    "schema": schema_filename,
                    "path": error.json_path,
                    "keyword": str(error.validator),
                    "message": error.message,
                },
            )
        )


def load_governance_yaml(path: Path, schema_filename: str) -> dict[str, Any]:
    """Read + canonical-check + schema-validate one governance document."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        halt(
            IntegrityHalt(
                "governance file unreadable",
                report={"path": str(path), "error": str(exc)},
            )
        )
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        halt(
            IntegrityHalt(
                "governance file is not valid YAML",
                report={"path": str(path), "error": str(exc)},
            )
        )
    check_payload(raw)
    # The governance schemas declare `type: object` at the root, so a
    # non-mapping document halts inside check_governance_instance.
    check_governance_instance(schema_filename, raw)
    return cast(dict[str, Any], raw)


class Policy:
    """The validated operational rulebook; every leaf path is a rule id."""

    def __init__(self, data: dict[str, Any], *, source: Path) -> None:
        self._data = data
        self._source = source
        self._sha256 = sha256_file(source)

    @classmethod
    def load(cls, path: Path, *, mode: Mode = "production") -> Policy:
        """Load and validate a decision policy (D1, D3).

        Args:
            path: Policy YAML file.
            mode: ``production`` requires ``meta.status: approved`` (D1);
                ``certification`` may load drafts.
        """
        data = load_governance_yaml(path, POLICY_SCHEMA_FILENAME)
        status = data["meta"]["status"]
        if mode == "production" and status != "approved":
            halt(
                IntegrityHalt(
                    "D1: production-mode load requires meta.status approved",
                    report={"path": str(path), "status": status},
                )
            )
        deletion = data["measurement"]["item_deletion"]
        if "preauthorized_rules" in deletion and not deletion["preauthorized"]:
            halt(
                IntegrityHalt(
                    "D3: preauthorized_rules present while preauthorized is false",
                    report={"path": str(path)},
                )
            )
        return cls(data, source=path)

    @property
    def version(self) -> str:
        """Policy version (cited as rule_version in every DecisionEntry)."""
        return str(self._data["meta"]["version"])

    @property
    def status(self) -> str:
        """meta.status — draft or approved (D1)."""
        return str(self._data["meta"]["status"])

    @property
    def sha256(self) -> str:
        """Content hash of the loaded policy file (manifest wiring, NFR-102)."""
        return self._sha256

    def _lookup(self, path: str) -> tuple[bool, Any]:
        node: Any = self._data
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return False, None
            node = node[part]
        return True, node

    def rule(self, path: str) -> Any:
        """Return the rule value (leaf or subtree copy) at a dotted path."""
        found, value = self._lookup(path)
        if not found:
            halt(
                IntegrityHalt(
                    "unresolved policy rule path",
                    report={"path": path, "policy_version": self.version},
                )
            )
        return copy.deepcopy(value)

    def verify_playbook_refs(self, playbook_path: Path) -> list[str]:
        """Resolve every playbook policy_ref against this policy (D2).

        Returns the references in playbook order (criteria ``policy_ref``s
        plus governance ``preauthorization_policy_ref``s); an unresolvable
        reference halts naming the missing path and the offending step.
        """
        try:
            playbook = yaml.safe_load(playbook_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            halt(
                IntegrityHalt(
                    "playbook unreadable for policy_ref verification",
                    report={"path": str(playbook_path), "error": str(exc)},
                )
            )
        refs: list[tuple[str, str]] = []
        for step in playbook.get("steps", []):
            step_id = str(step.get("id", "?"))
            for criterion in step.get("criteria", []):
                if "policy_ref" in criterion:
                    refs.append((str(criterion["policy_ref"]), step_id))
            governance = step.get("governance", {})
            if "preauthorization_policy_ref" in governance:
                refs.append((str(governance["preauthorization_policy_ref"]), step_id))
        for ref, step_id in refs:
            found, _ = self._lookup(ref)
            if not found:
                halt(
                    IntegrityHalt(
                        "D2: playbook policy_ref does not resolve in the decision policy",
                        report={"path": ref, "step": step_id},
                    )
                )
        return [ref for ref, _ in refs]

    def decide(
        self,
        *,
        log: DecisionLog,
        stage: str,
        decision_point: str,
        rule_id: str,
        inputs: dict[str, Any],
        decision: str,
        rationale: str,
        alternatives_considered: list[str] | None = None,
        flags: list[str] | None = None,
    ) -> DecisionEntry:
        """Resolve one operational judgment and log it (FR-1201).

        The cited ``rule_id`` must resolve in this policy; the entry carries
        this policy's version as ``rule_version``.
        """
        found, _ = self._lookup(rule_id)
        if not found:
            halt(
                IntegrityHalt(
                    "decide() cited a rule_id that does not resolve in the policy",
                    report={"path": rule_id, "decision_point": decision_point},
                )
            )
        fields: dict[str, Any] = {
            "stage": stage,
            "decision_point": decision_point,
            "rule_id": rule_id,
            "rule_version": self.version,
            "inputs": inputs,
            "decision": decision,
            "rationale": rationale,
        }
        if alternatives_considered is not None:
            fields["alternatives_considered"] = alternatives_considered
        if flags is not None:
            fields["flags"] = flags
        return log.append(fields)


class DecisionLog:
    """Append-only, gap-free decision log (the JSONL behind DECISION_LOG.md)."""

    def __init__(self, path: Path, clock: Clock) -> None:
        self._path = path
        self._clock = clock
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._next_seq = len(replay_decision_entries(path)) + 1

    @property
    def path(self) -> Path:
        """Location of the decision JSONL."""
        return self._path

    def append(self, fields: Mapping[str, object]) -> DecisionEntry:
        """Validate and append one entry, assigning ``seq``/``ts``."""
        payload: dict[str, Any] = dict(fields)
        for owned in _LOG_OWNED_FIELDS:
            if owned in payload:
                self._halt(
                    IntegrityHalt(
                        "log-owned field supplied by caller",
                        report={"field": owned},
                    )
                )
        with self._lock:
            payload["schema_version"] = 1
            payload["seq"] = self._next_seq
            payload["ts"] = self._stamp()
            try:
                entry = validate_and_build(DecisionEntry, payload)
            except BurhanHalt as exc:
                write_halt_report(exc, self._path.parent)  # already sink-emitted
                raise
            line = dump_canonical(entry)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            self._next_seq += 1
        return entry

    def _halt(self, exc: IntegrityHalt) -> NoReturn:
        halt_with_file(exc, self._path.parent)

    def _stamp(self) -> str:
        try:
            return format_utc_seconds(self._clock.now())
        except ValueError as exc:
            self._halt(
                IntegrityHalt(
                    "injected clock produced a non-canonical timestamp",
                    report={"error": str(exc)},
                )
            )


def replay_decision_entries(path: Path) -> list[DecisionEntry]:
    """Replay and validate the decision JSONL (gap-free seq enforced)."""
    if not path.exists():
        return []
    entries: list[DecisionEntry] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            halt(
                IntegrityHalt(
                    "decision log line is not valid JSON (external mutation?)",
                    report={"line": line_number, "error": str(exc)},
                )
            )
        entry = validate_and_build(DecisionEntry, raw)
        if entry.seq != line_number:
            halt(
                IntegrityHalt(
                    "decision log seq is not gap-free strictly increasing",
                    report={"line": line_number, "expected": line_number, "found": entry.seq},
                )
            )
        entries.append(entry)
    return entries


def render_decision_log(jsonl_path: Path) -> str:
    """Render DECISION_LOG.md purely from the JSONL entries.

    The rendered file adds nothing the entries do not contain
    (decision_log.schema.json): every line below is a projection of entry
    fields; dict payloads are embedded as canonical JSON.
    """
    entries = replay_decision_entries(jsonl_path)
    lines: list[str] = ["# DECISION_LOG", ""]
    for entry in entries:
        lines.append(f"## {entry.seq}. [{entry.stage}] {entry.decision_point}")
        lines.append(f"- ts: {format_utc_seconds(entry.ts)}")
        lines.append(f"- rule: {entry.rule_id} (policy v{entry.rule_version})")
        lines.append(f"- inputs: {dumps(entry.inputs)}")
        lines.append(f"- decision: {entry.decision}")
        lines.append(f"- rationale: {entry.rationale}")
        if entry.alternatives_considered is not None:
            lines.append(f"- alternatives considered: {dumps(entry.alternatives_considered)}")
        if entry.flags is not None:
            lines.append(f"- flags: {dumps(entry.flags)}")
        if entry.protected:
            lines.append("- protected: true (human decision on record)")
        lines.append("")
    return "\n".join(lines)
