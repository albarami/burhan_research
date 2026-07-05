"""Shared harness for the TC-15 integration tests (IT-1..IT-3).

Assembles a certification run from the realistic integration study: writes the
export, materializes governance in certification mode, constructs the stubbed
nodes, and builds the production registry. A certification-speed policy shrinks
the a-priori Monte-Carlo replications and the effects bootstrap resamples so the
wiring tests run in seconds — the statistics themselves are certified by the
unchanged module suites (AT-M15-5), not here. Both reductions are fixed, so the
IT-2 byte-identity rerun is unaffected.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from integration_study import build_integration_study, integration_config, study_document
from orch_util import manifest_fields
from stub_nodes import node_a_provider, node_c_approve_provider, stub_settings

from burhan.contract.node_a import NodeA
from burhan.core.orchestrator import Stage
from burhan.core.playbook import Playbook
from burhan.core.policy import Policy
from burhan.core.registry import Registry
from burhan.review.node_c import NodeC
from burhan.stages.registry import production_registry

REPO = Path(__file__).resolve().parents[2]
_PLAYBOOK_PATH = REPO / "playbooks" / "CB_SEM_PLAYBOOK_v1.0.yaml"
_TEMPLATE_POLICY = REPO / "policy" / "decision_policy.template.yaml"
_REGISTRY_PATH = REPO / "policy" / "protected_decisions.registry.yaml"


def fast_policy(tmp_path: Path, *, replications: int = 500, resamples: int = 1000) -> Policy:
    """The certified policy with the two expensive resample counts at their floors.

    The schema floors these (replications >= 500, resamples >= 1000), so this is
    the fastest legal certification policy — precision beyond the wiring is the
    module suites' job (AT-M15-5).
    """
    doc = yaml.safe_load(_TEMPLATE_POLICY.read_text(encoding="utf-8"))
    doc["power"]["montecarlo"]["replications"] = replications
    doc["effects"]["bootstrap"]["resamples"] = resamples
    path = tmp_path / "certification_speed_policy.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return Policy.load(path, mode="certification", playbook_path=_PLAYBOOK_PATH)


@dataclass(frozen=True)
class Certification:
    """A ready-to-run certification: registry + manifest fields + run dir."""

    registry: dict[str, Stage]
    manifest_fields: dict[str, Any]
    run_dir: Path
    study_dir: Path


def build_certification(tmp_path: Path, *, seed: int = 20260705, n: int = 300) -> Certification:
    """Write the study bundle and wire the full production registry over it."""
    study_dir = tmp_path / "study"
    (study_dir / "inputs").mkdir(parents=True)
    study = build_integration_study(seed, n=n)
    export_path = study.write(study_dir / "inputs")  # study/inputs/golden.csv
    policy = fast_policy(tmp_path)
    playbook = Playbook.load(_PLAYBOOK_PATH, mode="certification", policy=policy)
    decision_registry = Registry.load(_REGISTRY_PATH, mode="certification", policy=policy)
    node_a = NodeA(stub_settings(), provider_call=node_a_provider(integration_config()))
    node_c = NodeC(stub_settings(), provider_call=node_c_approve_provider())
    registry = production_registry(
        export_path=export_path,
        study_document=study_document(),
        header_rows=3,
        node_a=node_a,
        node_c=node_c,
        policy=policy,
        playbook=playbook,
        registry=decision_registry,
    )
    fields = dict(manifest_fields())
    fields["study_id"] = "integration-adoption-2026"
    return Certification(
        registry=registry,
        manifest_fields=fields,
        run_dir=tmp_path / "run",
        study_dir=study_dir,
    )
