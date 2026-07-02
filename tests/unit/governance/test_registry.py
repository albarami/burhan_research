"""Protected Decisions Registry tests (AT-M02-3 FIRST, AT-M02-4, R1/R2/D3).

The absence test leads (TC-02 Delivery Notes): the registry API exposes no
execution path for PD-01..PD-05 — enforcement is architectural (FR-1202).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from gov_util import (
    REGISTRY_TEMPLATE,
    FixedClock,
    load_yaml,
    policy_copy,
    registry_copy,
)

from burhan.core.errors import IntegrityHalt
from burhan.core.policy import DecisionLog, Policy
from burhan.core.registry import PermitToken, Recommendation, Registry

ALL_PD_IDS = ["PD-01", "PD-02", "PD-03", "PD-04", "PD-05"]


@pytest.fixture
def registry() -> Registry:
    return Registry.load(REGISTRY_TEMPLATE, mode="certification")


@pytest.fixture
def policy_default(tmp_path: Path) -> Policy:
    # Template defaults: item_deletion.preauthorized == false (FR-705).
    return Policy.load(policy_copy(tmp_path), mode="certification")


@pytest.fixture
def log(tmp_path: Path) -> DecisionLog:
    return DecisionLog(tmp_path / "decisions.jsonl", FixedClock())


def _evidence() -> dict[str, Any]:
    return {
        "item": "RS3",
        "construct": "RES",
        "signal": "loading_below_playbook_target",
        "loading": 0.41,
        "content_validity_note": "domain remains covered by RS1/RS2",
    }


# -- AT-M02-3 (absence) — written first ---------------------------------------


def test_registry_api_exposes_no_execution_path(registry: Registry) -> None:  # AT-M02-3
    public = {
        name
        for name in dir(registry)
        if not name.startswith("_") and callable(getattr(registry, name))
    }
    assert public == {"load", "entry", "guard", "verify_delegations"}
    forbidden = {
        "execute",
        "execute_protected",
        "apply",
        "apply_decision",
        "perform",
        "delete_item",
        "change_paradigm",
        "modify_hypothesis",
        "override",
    }
    assert not (forbidden & public)


@pytest.mark.parametrize(
    "name", ["execute", "execute_protected", "apply_decision", "perform", "override"]
)
def test_requesting_execution_raises_by_construction(
    registry: Registry, name: str
) -> None:  # AT-M02-3
    with pytest.raises(AttributeError):
        getattr(registry, name)


def test_guard_signature_admits_no_execution_flag(
    registry: Registry, policy_default: Policy, log: DecisionLog
) -> None:  # AT-M02-3
    with pytest.raises(TypeError):
        registry.guard(  # type: ignore[call-arg]
            "PD-05",
            policy=policy_default,
            log=log,
            stage="measurement",
            evidence=_evidence(),
            execute=True,
        )


def test_every_protected_decision_yields_recommendation_by_default(
    registry: Registry, policy_default: Policy, log: DecisionLog
) -> None:  # AT-M02-3 / FR-1202
    for decision_id in ALL_PD_IDS:
        outcome = registry.guard(
            decision_id,
            policy=policy_default,
            log=log,
            stage="measurement",
            evidence=_evidence(),
        )
        assert isinstance(outcome, Recommendation), decision_id
        assert outcome.decision_id == decision_id


# -- AT-M02-4 — protected path vs permit token --------------------------------


def test_deletion_candidate_yields_recommendation_and_unset_protected_entry(
    registry: Registry, policy_default: Policy, log: DecisionLog, tmp_path: Path
) -> None:  # AT-M02-4
    outcome = registry.guard(
        "PD-05",
        policy=policy_default,
        log=log,
        stage="measurement",
        evidence=_evidence(),
    )
    assert isinstance(outcome, Recommendation)
    assert outcome.system_response == "recommendation"
    assert outcome.evidence["item"] == "RS3"

    lines = (tmp_path / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    raw = json.loads(lines[0])
    assert raw["decision_point"] == "item_deletion_recommendation"
    assert raw["rule_id"] == "measurement.item_deletion.preauthorized"
    assert raw["rule_version"] == policy_default.version
    assert "protected" not in raw  # unset — the system never marks its own acts


def test_preauthorized_flip_yields_permit_token(
    registry: Registry, log: DecisionLog, tmp_path: Path
) -> None:  # AT-M02-4
    def preauthorize(data: dict[str, Any]) -> None:
        data["measurement"]["item_deletion"]["preauthorized"] = True
        data["measurement"]["item_deletion"]["preauthorized_rules"] = [
            "loading_below_playbook_target"
        ]

    policy = Policy.load(policy_copy(tmp_path, mutate=preauthorize), mode="certification")
    outcome = registry.guard(
        "PD-05", policy=policy, log=log, stage="measurement", evidence=_evidence()
    )
    assert isinstance(outcome, PermitToken)
    assert outcome.decision_id == "PD-05"
    assert outcome.delegation_ref == "measurement.item_deletion.preauthorized"
    assert outcome.policy_version == policy.version
    assert outcome.granted_rules == ("loading_below_playbook_target",)

    raw = json.loads((tmp_path / "decisions.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert raw["decision"] == "permit_token_issued"
    assert "protected" not in raw


def test_non_delegable_decisions_never_yield_tokens_even_when_preauthorized(
    registry: Registry, log: DecisionLog, tmp_path: Path
) -> None:  # FR-1202
    def preauthorize(data: dict[str, Any]) -> None:
        data["measurement"]["item_deletion"]["preauthorized"] = True

    policy = Policy.load(policy_copy(tmp_path, mutate=preauthorize), mode="certification")
    for decision_id in ["PD-01", "PD-02", "PD-03", "PD-04"]:
        outcome = registry.guard(
            decision_id, policy=policy, log=log, stage="structural", evidence=_evidence()
        )
        assert isinstance(outcome, Recommendation), decision_id


def test_guard_on_non_delegable_writes_no_decision_entry(
    registry: Registry, policy_default: Policy, log: DecisionLog, tmp_path: Path
) -> None:
    registry.guard(
        "PD-01", policy=policy_default, log=log, stage="structural", evidence=_evidence()
    )
    assert not (tmp_path / "decisions.jsonl").exists()  # no policy rule to cite


def test_guard_unknown_decision_id_halts(
    registry: Registry, policy_default: Policy, log: DecisionLog
) -> None:
    with pytest.raises(IntegrityHalt):
        registry.guard(
            "PD-99", policy=policy_default, log=log, stage="measurement", evidence=_evidence()
        )


# -- R1 / R2 / D3 load and cross-checks ---------------------------------------


def test_template_registry_validates_and_draft_blocks_production(tmp_path: Path) -> None:
    Registry.load(REGISTRY_TEMPLATE, mode="certification")  # draft OK here
    with pytest.raises(IntegrityHalt) as excinfo:
        Registry.load(REGISTRY_TEMPLATE, mode="production")  # R1
    assert "R1" in excinfo.value.message
    approved = registry_copy(tmp_path, status="approved")
    assert Registry.load(approved, mode="production").status == "approved"


def test_duplicate_pd_ids_halt(tmp_path: Path) -> None:  # R1
    def duplicate(data: dict[str, Any]) -> None:
        data["protected_decisions"][1]["id"] = "PD-01"

    with pytest.raises(IntegrityHalt) as excinfo:
        Registry.load(registry_copy(tmp_path, mutate=duplicate), mode="certification")
    assert "PD-01" in str(excinfo.value.to_report()["details"])


def test_schema_violation_halts_with_path(tmp_path: Path) -> None:
    def corrupt(data: dict[str, Any]) -> None:
        data["protected_decisions"][0]["enforcement"] = "soft_suggestion"

    with pytest.raises(IntegrityHalt) as excinfo:
        Registry.load(registry_copy(tmp_path, mutate=corrupt), mode="certification")
    assert "enforcement" in excinfo.value.to_report()["details"]["path"]


def test_delegation_ref_resolves_against_policy(
    registry: Registry, policy_default: Policy
) -> None:  # AT-M02-2 (R2)
    registry.verify_delegations(policy_default)  # template pair resolves


def test_unresolvable_delegation_ref_halts_naming_path(
    tmp_path: Path, policy_default: Policy
) -> None:  # AT-M02-2 (R2)
    def bogus(data: dict[str, Any]) -> None:
        data["protected_decisions"][4]["delegation_ref"] = "measurement.no_such.rule"

    broken = Registry.load(registry_copy(tmp_path, mutate=bogus), mode="certification")
    with pytest.raises(IntegrityHalt) as excinfo:
        broken.verify_delegations(policy_default)
    assert excinfo.value.to_report()["details"]["path"] == "measurement.no_such.rule"


def test_pd05_delegation_must_point_at_item_deletion_switch(
    tmp_path: Path, policy_default: Policy
) -> None:  # D3
    def misdirect(data: dict[str, Any]) -> None:
        data["protected_decisions"][4]["delegation_ref"] = "gates.max_retries"  # real leaf

    misdirected = Registry.load(registry_copy(tmp_path, mutate=misdirect), mode="certification")
    with pytest.raises(IntegrityHalt) as excinfo:
        misdirected.verify_delegations(policy_default)
    assert "D3" in excinfo.value.message


def test_entry_returns_readonly_copy(registry: Registry) -> None:
    entry = registry.entry("PD-05")
    assert entry["delegable"] is True
    entry["delegable"] = False  # mutating the copy must not touch the registry
    assert registry.entry("PD-05")["delegable"] is True
    with pytest.raises(IntegrityHalt):
        registry.entry("PD-42")


def test_registry_template_content_matches_governed_file(registry: Registry) -> None:
    governed = load_yaml(REGISTRY_TEMPLATE)
    assert [pd["id"] for pd in governed["protected_decisions"]] == ALL_PD_IDS
    assert registry.entry("PD-05")["delegation_ref"] == "measurement.item_deletion.preauthorized"
