"""The production stage registry (TC-15): the fixed 13-stage DAG, wired.

``production_registry`` builds every stage the orchestrator needs — the ten
Stage-1A adapters over the certified modules plus the three Stage-1B
certification pass-through stubs — from injected governance, nodes, and study
inputs. Nodes are injected (real providers in production; deterministic canned
providers under certification) so the same wiring serves both. The returned
mapping is keyed by stage name and covers ``orchestrator.PIPELINE`` exactly and
in order (AT-M15-4).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from burhan.core.orchestrator import PIPELINE, Stage
from burhan.stages.stage_1a import (
    Assumptions,
    Contract,
    Effects,
    Gate1,
    Ingest,
    Measurement,
    Power,
    Prep,
    Robustness,
    Structural,
)
from burhan.stages.stub_1b import StubGate2, StubNarrate, StubPackage

if TYPE_CHECKING:
    from pathlib import Path

    from burhan.contract.node_a import ContractProvenance, NodeA
    from burhan.core.playbook import Playbook
    from burhan.core.policy import Policy
    from burhan.core.registry import Registry as DecisionRegistry
    from burhan.review.node_c import NodeC


def production_registry(
    *,
    export_path: Path,
    study_document: str,
    header_rows: int,
    node_a: NodeA,
    node_c: NodeC,
    policy: Policy,
    playbook: Playbook,
    registry: DecisionRegistry,
    data_dictionary: str | None = None,
    montecarlo_replications: int | None = None,
    marker_items: list[str] | None = None,
    provenance: ContractProvenance | None = None,
) -> dict[str, Stage]:
    """Every fixed-DAG stage, keyed by name, in DAG order (AT-M15-4).

    ``marker_items`` names any method-marker items the study declares for the
    PB-12 CLF/marker CMB test (none under the certification study, which fits
    within bands and declares no marker — PB-12/PB-14 flag there).
    """
    stages: list[Stage] = [
        Ingest(export_path=export_path, header_rows=header_rows),
        Contract(
            node_a=node_a,
            study_document=study_document,
            data_dictionary=data_dictionary,
            provenance=provenance,
        ),
        Gate1(node_c=node_c, study_document=study_document),
        Power(policy=policy, playbook=playbook, montecarlo_replications=montecarlo_replications),
        Prep(export_path=export_path, policy=policy, playbook=playbook),
        Assumptions(policy=policy, playbook=playbook),
        Measurement(policy=policy, playbook=playbook, registry=registry, marker_items=marker_items),
        Structural(playbook=playbook),
        Effects(policy=policy, playbook=playbook),
        Robustness(playbook=playbook),
        StubNarrate(playbook=playbook),
        StubGate2(),
        StubPackage(playbook=playbook),
    ]
    built = {stage.name: stage for stage in stages}
    # Fail loudly here rather than deep in the orchestrator if wiring drifts.
    if tuple(built) != PIPELINE:
        raise AssertionError(f"registry order {tuple(built)} != DAG {PIPELINE}")
    return built
