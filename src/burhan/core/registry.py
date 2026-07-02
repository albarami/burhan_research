"""Protected Decisions Registry enforcement (FR-1202; Concept §10.2).

The registry enumerates decisions the system is architecturally forbidden to
take. This module's public surface is deliberately incapable of executing
any of them: :meth:`Registry.guard` returns a :class:`Recommendation` — or,
for the single delegable decision (PD-05) behind its explicit policy switch,
a :class:`PermitToken` consumed only by M10's deletion protocol. **There is
no execute method anywhere** (AT-M02-3 proves this by introspection).

Loader cross-checks: R1 (unique PD ids; ``meta.status: approved`` required
for production loads), R2 (every ``delegation_ref`` resolves to a policy
path), and D3's pointer rule (PD-05 must delegate to
``measurement.item_deletion.preauthorized``). R3 (registry hash in every run
manifest) is served by :attr:`Registry.sha256`.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from burhan.core.artifacts.canonical import sha256_file
from burhan.core.errors import IntegrityHalt, halt
from burhan.core.policy import (
    REGISTRY_SCHEMA_FILENAME,
    DecisionLog,
    Mode,
    Policy,
    load_governance_yaml,
)

_PD05_DELEGATION_TARGET = "measurement.item_deletion.preauthorized"
_PD05_RULES_PATH = "measurement.item_deletion.preauthorized_rules"


@dataclass(frozen=True)
class Recommendation:
    """A surfaced protected-decision candidate; acting on it is human-only."""

    decision_id: str
    title: str
    enforcement: str
    system_response: str
    evidence: dict[str, Any]


@dataclass(frozen=True)
class PermitToken:
    """Evidence of explicit pre-authorization for the one delegable decision.

    Issued only for PD-05 when ``measurement.item_deletion.preauthorized``
    is true; consumed exclusively by M10's deletion protocol (PB-13), which
    remains bound in full even under delegation.
    """

    decision_id: str
    delegation_ref: str
    policy_version: str
    granted_rules: tuple[str, ...]


class Registry:
    """Loaded, validated Protected Decisions Registry (recommendation-only)."""

    def __init__(self, data: dict[str, Any], *, source: Path) -> None:
        self._data = data
        self._source = source
        self._sha256 = sha256_file(source)
        self._entries: dict[str, dict[str, Any]] = {
            str(entry["id"]): entry for entry in data["protected_decisions"]
        }

    @classmethod
    def load(
        cls, path: Path, *, mode: Mode = "production", policy: Policy | None = None
    ) -> Registry:
        """Load and validate the registry (R1; R2/D3 at load when possible).

        AT-M02-2 requires delegation_refs to resolve AT LOAD: when ``policy``
        is given (any mode) the R2/D3 cross-checks run before this returns,
        and production mode REQUIRES it. :func:`load_governance` is the
        documented load path composing all governance cross-checks.
        """
        data = load_governance_yaml(path, REGISTRY_SCHEMA_FILENAME)
        status = data["meta"]["status"]
        if mode == "production" and status != "approved":
            halt(
                IntegrityHalt(
                    "R1: production-mode load requires meta.status approved",
                    report={"path": str(path), "status": status},
                )
            )
        seen: set[str] = set()
        for entry in data["protected_decisions"]:
            decision_id = str(entry["id"])
            if decision_id in seen:
                halt(
                    IntegrityHalt(
                        "R1: duplicate protected-decision id",
                        report={"path": str(path), "id": decision_id},
                    )
                )
            seen.add(decision_id)
        if mode == "production" and policy is None:
            halt(
                IntegrityHalt(
                    "R2: production-mode load requires the decision policy so "
                    "delegation_refs resolve at load (AT-M02-2)",
                    report={"path": str(path)},
                )
            )
        registry = cls(data, source=path)
        if policy is not None:
            registry.verify_delegations(policy)
        return registry

    @property
    def status(self) -> str:
        """meta.status — draft or approved (R1)."""
        return str(self._data["meta"]["status"])

    @property
    def sha256(self) -> str:
        """Content hash of the loaded registry file (R3; manifest wiring)."""
        return self._sha256

    def entry(self, decision_id: str) -> dict[str, Any]:
        """Return a read-only copy of one registry entry."""
        entry = self._entries.get(decision_id)
        if entry is None:
            halt(
                IntegrityHalt(
                    "unknown protected-decision id",
                    report={"id": decision_id, "known": sorted(self._entries)},
                )
            )
        return copy.deepcopy(entry)

    def verify_delegations(self, policy: Policy) -> None:
        """Cross-check every delegation against the policy (R2 + D3 pointer).

        Every ``delegation_ref`` must resolve to a policy path, and PD-05 —
        the only delegable decision — must point at exactly
        ``measurement.item_deletion.preauthorized``.
        """
        for decision_id, entry in self._entries.items():
            if not entry.get("delegable", False):
                continue
            ref = str(entry["delegation_ref"])
            found, _ = policy._lookup(ref)  # noqa: SLF001 — same-layer cross-check
            if not found:
                halt(
                    IntegrityHalt(
                        "R2: delegation_ref does not resolve in the decision policy",
                        report={"id": decision_id, "path": ref},
                    )
                )
            if decision_id == "PD-05" and ref != _PD05_DELEGATION_TARGET:
                halt(
                    IntegrityHalt(
                        "D3: PD-05 delegation must point at "
                        "measurement.item_deletion.preauthorized",
                        report={"id": decision_id, "path": ref},
                    )
                )

    def guard(
        self,
        decision_id: str,
        *,
        policy: Policy,
        log: DecisionLog,
        stage: str,
        evidence: dict[str, Any],
    ) -> Recommendation | PermitToken:
        """Consult the protected boundary for one decision (FR-1202).

        Returns a :class:`Recommendation` for every decision by default. For
        PD-05 only, with the delegation switch true in the policy, returns a
        :class:`PermitToken` instead. Both PD-05 outcomes write a
        DecisionEntry citing the delegation switch as the rule fired
        (FR-1201); ``protected`` stays unset — the system never marks its
        own actions as human decisions. Non-delegable consultations write no
        decision entry (no policy rule exists to cite); their record is the
        advisory path (FR-1203).
        """
        entry = self.entry(decision_id)
        if not entry.get("delegable", False):
            return Recommendation(
                decision_id=decision_id,
                title=str(entry["title"]),
                enforcement=str(entry["enforcement"]),
                system_response=str(entry["system_response"]),
                evidence=evidence,
            )
        ref = str(entry["delegation_ref"])
        preauthorized = bool(policy.rule(ref))
        if not preauthorized:
            log.append(
                {
                    "stage": stage,
                    "decision_point": "item_deletion_recommendation",
                    "rule_id": ref,
                    "rule_version": policy.version,
                    "inputs": evidence,
                    "decision": "recommendation_surfaced",
                    "rationale": (
                        "Protected by default (FR-705): candidate surfaced for human "
                        "approval; no autonomous deletion path exists."
                    ),
                }
            )
            return Recommendation(
                decision_id=decision_id,
                title=str(entry["title"]),
                enforcement=str(entry["enforcement"]),
                system_response=str(entry["system_response"]),
                evidence=evidence,
            )
        found, rules = policy._lookup(_PD05_RULES_PATH)  # noqa: SLF001
        granted = tuple(str(rule) for rule in rules) if found and rules else ()
        log.append(
            {
                "stage": stage,
                "decision_point": "item_deletion_recommendation",
                "rule_id": ref,
                "rule_version": policy.version,
                "inputs": evidence,
                "decision": "permit_token_issued",
                "rationale": (
                    "Deletion pre-authorized by explicit policy delegation (PD-05); "
                    "PB-13 protocol binds in full at execution (M10)."
                ),
            }
        )
        return PermitToken(
            decision_id=decision_id,
            delegation_ref=ref,
            policy_version=policy.version,
            granted_rules=granted,
        )


@dataclass(frozen=True)
class Governance:
    """The cross-checked policy + registry pair produced by the load path."""

    policy: Policy
    registry: Registry


def load_governance(
    *,
    policy_path: Path,
    registry_path: Path,
    playbook_path: Path,
    mode: Mode = "production",
) -> Governance:
    """THE documented governance load path (AT-M02-2: refs resolve at load).

    Loads the policy (D1/D3), resolves every playbook policy_ref against it
    (D2), loads the registry (R1), and resolves every delegation_ref (R2 +
    the D3 pointer rule) — all before returning. An unresolved reference
    fails this load with the missing path named; no partially-checked
    governance object ever escapes.
    """
    policy = Policy.load(policy_path, mode=mode, playbook_path=playbook_path)
    registry = Registry.load(registry_path, mode=mode, policy=policy)
    return Governance(policy=policy, registry=registry)
