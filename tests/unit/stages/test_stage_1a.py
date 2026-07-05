"""TC-15 Stage-1A adapters: the non-R stages and the registry shape.

Ingest (raw-N accounting), Contract (Node A extraction), and Gate1 (Node C
review) run without the R worker, so they are unit-tested here in isolation.
The R-backed analytic stages (power/prep/assumptions/measurement/structural/
effects/robustness) are exercised end-to-end by IT-1. The production registry's
shape — exactly the 13 fixed-DAG stages in order — is AT-M15-4.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from integration_study import build_integration_study, study_document
from stages_util import stage_context
from stub_nodes import node_a_provider, node_c_approve_provider, stub_settings

from burhan.contract.node_a import NodeA
from burhan.core.errors import GateExhausted
from burhan.core.orchestrator import PIPELINE
from burhan.core.playbook import Playbook
from burhan.core.policy import Policy
from burhan.core.registry import Registry
from burhan.review.node_c import NodeC
from burhan.stages import context
from burhan.stages.registry import production_registry
from burhan.stages.stage_1a import Contract, Gate1, Ingest

REPO = Path(__file__).resolve().parents[3]


def _policy() -> Policy:
    return Policy.load(
        REPO / "policy" / "decision_policy.template.yaml",
        mode="certification",
        playbook_path=REPO / "playbooks" / "CB_SEM_PLAYBOOK_v1.0.yaml",
    )


def _decision_registry(policy: Policy) -> Registry:
    return Registry.load(
        REPO / "policy" / "protected_decisions.registry.yaml", mode="certification", policy=policy
    )


def _node_a(config: dict[str, object]) -> NodeA:
    return NodeA(stub_settings(), provider_call=node_a_provider(config))


def test_ingest_records_the_raw_n_and_export_fingerprint(tmp_path: Path) -> None:
    study = build_integration_study(20260705, n=20)
    export = study.write(tmp_path)
    ctx = stage_context(tmp_path / "run", stage="ingest")
    Ingest(export_path=export, header_rows=3).execute(ctx)
    summary = json.loads((ctx.run_dir / context.INGEST_SUMMARY).read_text(encoding="utf-8"))
    assert summary["raw_n"] == 20  # 23 csv rows - 3 header rows
    assert len(summary["export_sha256"]) == 64


def test_contract_extracts_and_persists_the_study_config(tmp_path: Path) -> None:
    study = build_integration_study(20260705, n=20)
    ctx = stage_context(tmp_path / "run", stage="contract")
    Contract(node_a=_node_a(study.config), study_document=study_document()).execute(ctx)
    config = context.load_config(ctx)
    assert config.meta.study_id == "integration-adoption-2026"
    assert {h.id for h in config.hypotheses} == {"H1", "H2", "H3", "H4"}


def test_gate1_approve_writes_verdict_and_continues(tmp_path: Path) -> None:
    study = build_integration_study(20260705, n=20)
    ctx = stage_context(tmp_path / "run", stage="gate1")
    Contract(node_a=_node_a(study.config), study_document=study_document()).execute(ctx)
    node_c = NodeC(stub_settings(), provider_call=node_c_approve_provider())
    Gate1(node_c=node_c, study_document=study_document()).execute(ctx)
    verdict = json.loads((ctx.run_dir / "gate1" / "verdict.json").read_text(encoding="utf-8"))
    assert verdict["verdict"] == "approve"


def test_gate1_reject_exhausts_the_gate(tmp_path: Path) -> None:
    study = build_integration_study(20260705, n=20)
    ctx = stage_context(tmp_path / "run", stage="gate1")
    Contract(node_a=_node_a(study.config), study_document=study_document()).execute(ctx)

    def _reject(_prompt: str) -> str:
        return yaml.safe_dump({"verdict": "reject", "fixes": ["restate H4"]}, sort_keys=True)

    node_c = NodeC(stub_settings(), provider_call=_reject)
    with pytest.raises(GateExhausted):
        Gate1(node_c=node_c, study_document=study_document()).execute(ctx)


def test_production_registry_is_exactly_the_dag_in_order(tmp_path: Path) -> None:
    study = build_integration_study(20260705, n=20)
    policy = _policy()
    playbook = Playbook.load(
        REPO / "playbooks" / "CB_SEM_PLAYBOOK_v1.0.yaml", mode="certification", policy=policy
    )
    registry = production_registry(
        export_path=tmp_path / "export.csv",
        study_document=study_document(),
        header_rows=3,
        node_a=_node_a(study.config),
        node_c=NodeC(stub_settings(), provider_call=node_c_approve_provider()),
        policy=policy,
        playbook=playbook,
        registry=_decision_registry(policy),
    )
    assert tuple(registry) == PIPELINE
    assert len(registry) == 13
