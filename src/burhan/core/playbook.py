"""Playbook engine: loader with P1–P5, accessors, methodology binding.

The playbook is the method owner's adopted position codified (Concept §4);
this loader reproduces the Wave-2 validation script as production code
(TC-03 Delivery Notes). Cross-checks per playbook.schema.yaml:82-87:

- **P1** — step ids unique and ordered; stages appear in pipeline order.
- **P2** — the citation registry and the keys used by steps match exactly.
- **P3** — every ``policy_ref`` (and governance ``preauthorization_policy_ref``)
  resolves against the decision policy AT LOAD; production loads require the
  policy (the AT-M02-2 rule applied here).
- **P4** — every ``outputs`` prefix conforms to the statistic-ID grammar.
- **P5** — ``meta.status: approved`` required for production loads.

Method binding (FR-1302/1303): :meth:`Playbook.for_methodology` loads exactly
the declared playbook; an unknown methodology or a metadata mismatch is a
clean refusal — sink-only halt, no partial run artifacts.
"""

from __future__ import annotations

import copy
import re
from functools import cache
from pathlib import Path
from typing import Any

# Untyped third-party edges (no stubs in the locked dependency set).
import yaml  # type: ignore[import-untyped]
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import best_match  # type: ignore[import-untyped]

from burhan.core.artifacts.canonical import check_payload, sha256_file
from burhan.core.errors import IntegrityHalt, halt
from burhan.core.policy import Mode, Policy

PLAYBOOK_SCHEMA_FILENAME = "playbook.schema.yaml"

PIPELINE_STAGE_ORDER = (
    "power",
    "prep",
    "assumptions",
    "measurement",
    "structural",
    "effects",
    "robustness",
    "narrate",
    "package",
)

# Statistic-ID prefix grammar (schemas/00_README.md; Wave-2 script verbatim).
OUTPUT_PREFIX_PATTERN = re.compile(
    r"^(power|prep|assumptions|measurement|structural|effects|robustness)\.[a-z_]+$"
)


def playbooks_dir() -> Path:
    """Location of the governed playbooks (repo ``playbooks/``)."""
    return Path(__file__).resolve().parents[3] / "playbooks"


_default_playbooks_dir = playbooks_dir


@cache
def _validator() -> Draft202012Validator:
    schema = yaml.safe_load(
        (playbooks_dir() / PLAYBOOK_SCHEMA_FILENAME).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _check_schema(instance: object, path: Path) -> None:
    error = best_match(_validator().iter_errors(instance))
    if error is not None:
        halt(
            IntegrityHalt(
                f"schema violation [playbook] at {error.json_path}: {error.message}",
                report={
                    "playbook": str(path),
                    "path": error.json_path,
                    "keyword": str(error.validator),
                    "message": error.message,
                },
            )
        )


class Playbook:
    """A loaded, cross-checked playbook; the curriculum the engine executes."""

    def __init__(self, data: dict[str, Any], *, source: Path) -> None:
        self._data = data
        self._source = source
        self._sha256 = sha256_file(source)
        self._steps: dict[str, dict[str, Any]] = {str(step["id"]): step for step in data["steps"]}

    @classmethod
    def load(
        cls, path: Path, *, mode: Mode = "production", policy: Policy | None = None
    ) -> Playbook:
        """Load and cross-check one playbook file (P1–P5).

        Args:
            path: Playbook YAML file.
            mode: ``production`` requires ``meta.status: approved`` (P5) and a
                ``policy`` for ref resolution (P3); ``certification`` may load
                drafts and pieces in isolation.
            policy: Decision policy against which every ``policy_ref`` must
                resolve (P3); required in production mode.
        """
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            halt(
                IntegrityHalt(
                    "playbook file unreadable",
                    report={"path": str(path), "error": str(exc)},
                )
            )
        try:
            raw = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            halt(
                IntegrityHalt(
                    "playbook file is not valid YAML",
                    report={"path": str(path), "error": str(exc)},
                )
            )
        check_payload(raw)
        _check_schema(raw, path)
        data: dict[str, Any] = raw

        status = data["meta"]["status"]
        if mode == "production" and status != "approved":
            halt(
                IntegrityHalt(
                    "P5: production-mode load requires meta.status approved",
                    report={"path": str(path), "status": status},
                )
            )

        steps: list[dict[str, Any]] = data["steps"]
        _check_p1(steps, path)
        _check_p2(data, path)
        _check_p4(steps, path)

        if mode == "production" and policy is None:
            halt(
                IntegrityHalt(
                    "P3: production-mode load requires the decision policy so "
                    "policy_refs resolve at load",
                    report={"path": str(path)},
                )
            )
        if policy is not None:
            _check_p3(steps, policy, path)
        return cls(data, source=path)

    @classmethod
    def for_methodology(
        cls,
        declared: str,
        playbook_id: str,
        playbook_version: str,
        *,
        mode: Mode = "production",
        policy: Policy | None = None,
        playbooks_dir: Path | None = None,
    ) -> Playbook:
        """Load EXACTLY the contract-declared playbook (FR-1302/1303).

        An unknown methodology, a missing playbook file, or a metadata
        mismatch produces the clean refusal — a sink-only halt that creates
        no partial run artifacts (no playbook, no run).
        """
        directory = playbooks_dir if playbooks_dir is not None else _default_playbooks_dir()
        expected = directory / f"{playbook_id}_v{playbook_version}.yaml"
        if not expected.is_file():
            halt(
                IntegrityHalt(
                    "no playbook, no run: the declared methodology has no playbook "
                    "(FR-1302); the system refuses cleanly rather than improvises",
                    report={
                        "methodology": declared,
                        "playbook_id": playbook_id,
                        "playbook_version": playbook_version,
                        "expected_file": str(expected),
                    },
                )
            )
        playbook = cls.load(expected, mode=mode, policy=policy)
        if (
            playbook.methodology != declared
            or playbook.id != playbook_id
            or playbook.version != playbook_version
        ):
            halt(
                IntegrityHalt(
                    "method binding violation (FR-1303): the engine loads exactly "
                    "the declared playbook, and this file does not match",
                    report={
                        "declared": declared,
                        "playbook_id": playbook_id,
                        "playbook_version": playbook_version,
                        "file_methodology": playbook.methodology,
                        "file_id": playbook.id,
                        "file_version": playbook.version,
                    },
                )
            )
        return playbook

    # -- accessors -------------------------------------------------------------

    @property
    def id(self) -> str:
        """meta.id — e.g. CB_SEM_PLAYBOOK."""
        return str(self._data["meta"]["id"])

    @property
    def version(self) -> str:
        """meta.version — recorded in every run manifest (NFR-102)."""
        return str(self._data["meta"]["version"])

    @property
    def methodology(self) -> str:
        """meta.methodology — the method this playbook executes."""
        return str(self._data["meta"]["methodology"])

    @property
    def status(self) -> str:
        """meta.status — draft or approved (P5)."""
        return str(self._data["meta"]["status"])

    @property
    def sha256(self) -> str:
        """Content hash of the loaded playbook file (NFR-102)."""
        return self._sha256

    @property
    def step_ids(self) -> list[str]:
        """Every step id in playbook order."""
        return list(self._steps)

    @property
    def chapter_structure(self) -> list[str]:
        """Canonical findings chapter order (FR-1004)."""
        return list(self._data["reporting"]["chapter_structure"])

    def step(self, step_id: str) -> dict[str, Any]:
        """Return a read-only copy of one step."""
        step = self._steps.get(step_id)
        if step is None:
            halt(
                IntegrityHalt(
                    "unknown playbook step",
                    report={"step": step_id, "known": list(self._steps)},
                )
            )
        return copy.deepcopy(step)

    def criteria(self, step_id: str) -> list[dict[str, Any]]:
        """Return a read-only copy of one step's criteria."""
        return list(self.step(step_id).get("criteria", []))

    def outputs(self, step_id: str) -> list[str]:
        """Results-store ID prefixes this step must emit (FR-1106)."""
        return [str(prefix) for prefix in self.step(step_id).get("outputs", [])]

    def citation(self, key: str) -> str:
        """Full reference string for a citation key."""
        citations: dict[str, str] = self._data["citations"]
        if key not in citations:
            halt(
                IntegrityHalt(
                    "unknown citation key",
                    report={"key": key, "known": sorted(citations)},
                )
            )
        return str(citations[key])


def _check_p1(steps: list[dict[str, Any]], path: Path) -> None:
    seen: set[str] = set()
    numbers: list[int] = []
    for step in steps:
        step_id = str(step["id"])
        if step_id in seen:
            halt(
                IntegrityHalt(
                    "P1: duplicate step ids",
                    report={"path": str(path), "step": step_id},
                )
            )
        seen.add(step_id)
        # id shape PB-nn is schema-guaranteed (pattern ^PB-[0-9]{2}$).
        numbers.append(int(step_id[3:]))
    if numbers != sorted(numbers):
        halt(
            IntegrityHalt(
                "P1: step id order violated",
                report={"path": str(path), "ids": [s["id"] for s in steps]},
            )
        )
    stages = [str(step["stage"]) for step in steps]
    if stages != sorted(stages, key=PIPELINE_STAGE_ORDER.index):
        halt(
            IntegrityHalt(
                "P1: stage order violated; stages must appear in pipeline order",
                report={"path": str(path), "stages": stages},
            )
        )


def _check_p2(data: dict[str, Any], path: Path) -> None:
    registered = set(data["citations"])
    used: set[str] = set()
    for step in data["steps"]:
        used |= {str(key) for key in step["citations"]}
        for criterion in step.get("criteria", []):
            used |= {str(key) for key in criterion.get("citation_keys", [])}
    if used != registered:
        halt(
            IntegrityHalt(
                "P2: citation registry and used keys do not match",
                report={
                    "path": str(path),
                    "used_not_registered": sorted(used - registered),
                    "registered_not_used": sorted(registered - used),
                },
            )
        )


def _check_p4(steps: list[dict[str, Any]], path: Path) -> None:
    for step in steps:
        for prefix in step.get("outputs", []):
            if not OUTPUT_PREFIX_PATTERN.fullmatch(str(prefix)):
                halt(
                    IntegrityHalt(
                        "P4: outputs prefix violates the statistic-ID grammar",
                        report={"path": str(path), "step": str(step["id"]), "prefix": str(prefix)},
                    )
                )


def _check_p3(steps: list[dict[str, Any]], policy: Policy, path: Path) -> None:
    for step in steps:
        step_id = str(step["id"])
        refs = [
            str(criterion["policy_ref"])
            for criterion in step.get("criteria", [])
            if "policy_ref" in criterion
        ]
        governance = step.get("governance", {})
        if "preauthorization_policy_ref" in governance:
            refs.append(str(governance["preauthorization_policy_ref"]))
        for ref in refs:
            found, _ = policy._lookup(ref)  # noqa: SLF001 — same-layer cross-check
            if not found:
                halt(
                    IntegrityHalt(
                        "P3: policy_ref does not resolve in the decision policy",
                        report={"path": ref, "step": step_id, "playbook": str(path)},
                    )
                )
