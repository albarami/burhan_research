"""Certification run mode (TC-15, D2): a network-free ``burhan run``.

The certified-workstation dry run has no operator and no provider egress. This
wires the production registry over a self-contained study bundle
(``config/study_config.yaml`` + ``inputs/``) with deterministic canned nodes —
Node A echoes the pre-extracted contract, Node C approves — so a golden study
traverses the full DAG offline. Production (draft-governance, real providers)
runs land with a later contract; this module owns only the certification path.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import platform
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from burhan.contract.llm_base import LlmSettings, NodeSettings
from burhan.contract.node_a import NodeA
from burhan.core.artifacts.clock import Clock
from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig, format_utc_seconds
from burhan.core.orchestrator import Orchestrator, RunResult, Stage
from burhan.core.playbook import Playbook, playbooks_dir
from burhan.core.policy import Policy, governance_dir
from burhan.core.registry import Registry
from burhan.review.node_c import NodeC
from burhan.stages.registry import production_registry

_PLAYBOOK = "CB_SEM_PLAYBOOK_v1.0.yaml"
_POLICY = "decision_policy.template.yaml"
_REGISTRY = "protected_decisions.registry.yaml"
_MASTER_SEED = 20260705
_APPROVE = yaml.safe_dump({"verdict": "approve", "fixes": []}, sort_keys=True)


class SystemClock:
    """Whole-second UTC wall clock (the production ``Clock``)."""

    def now(self) -> dt.datetime:
        return dt.datetime.now(dt.UTC).replace(microsecond=0)


def _node_settings(*, provider: str, lineage: str) -> NodeSettings:
    return NodeSettings(
        provider=provider,
        model="certification-canned",
        lineage=lineage,
        temperature=0.0,
        api_key_env="ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY",
        max_retries=2,
    )


def certification_settings() -> LlmSettings:
    """Pinned, schema-valid settings for the canned certification nodes."""
    return LlmSettings(
        nodes={
            "node_a": _node_settings(provider="anthropic", lineage="anthropic.claude"),
            "node_b": _node_settings(provider="anthropic", lineage="anthropic.claude"),
            "node_c": _node_settings(provider="openai", lineage="openai.gpt"),
        },
        source_sha256="0" * 64,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _node_manifest(*, provider: str, lineage: str) -> dict[str, Any]:
    return {
        "provider": provider,
        "model": "certification-canned",
        "lineage": lineage,
        "temperature": 0,
    }


def _manifest_fields(config: StudyConfig, run_id: str) -> dict[str, Any]:
    node_a = _node_manifest(provider="anthropic", lineage="anthropic.claude")
    node_c = _node_manifest(provider="openai", lineage="openai.gpt")
    prompt = {"version": "1.0", "sha256": "0" * 64}
    return {
        "run_id": run_id,
        "study_id": config.meta.study_id,
        "master_seed": _MASTER_SEED,
        "engine": {"version": "0.1.0", "git_commit": "0000000", "git_dirty": False},
        "hashes": {
            "study_config": _sha256(governance_dir() / _POLICY),
            "decision_policy": _sha256(governance_dir() / _POLICY),
            "protected_registry": _sha256(governance_dir() / _REGISTRY),
            "playbook": _sha256(playbooks_dir() / _PLAYBOOK),
            "prompts": {"node_a": prompt, "node_b": prompt, "node_c": prompt},
            "uv_lock": "0" * 64,
            "renv_lock": "0" * 64,
        },
        "environment": {
            "python": platform.python_version(),
            "r": "4.5",
            "os": platform.system(),
            "doctor_passed": True,
        },
        "llm_nodes": {"node_a": node_a, "node_b": node_a, "node_c": node_c},
    }


def _build_registry(
    study_dir: Path, the_policy: Policy, montecarlo_replications: int | None
) -> tuple[dict[str, Stage], StudyConfig]:
    config_text = (study_dir / "config" / "study_config.yaml").read_text(encoding="utf-8")
    config = validate_and_build(StudyConfig, yaml.safe_load(config_text))
    export_path = sorted((study_dir / "inputs").glob("*.csv"))[0]
    study_document = (study_dir / "inputs" / "study_document.txt").read_text(encoding="utf-8")
    playbook = Playbook.load(playbooks_dir() / _PLAYBOOK, mode="certification", policy=the_policy)
    decision_registry = Registry.load(
        governance_dir() / _REGISTRY, mode="certification", policy=the_policy
    )
    header_rows = config.data.header_rows if config.data.header_rows is not None else 3
    registry = production_registry(
        export_path=export_path,
        study_document=study_document,
        header_rows=header_rows,
        node_a=NodeA(certification_settings(), provider_call=lambda _prompt: config_text),
        node_c=NodeC(certification_settings(), provider_call=lambda _prompt: _APPROVE),
        policy=the_policy,
        playbook=playbook,
        registry=decision_registry,
        montecarlo_replications=montecarlo_replications,
    )
    return registry, config


def certification_run(
    study_dir: Path,
    *,
    clock: Clock | None = None,
    policy: Policy | None = None,
    montecarlo_replications: int | None = None,
) -> RunResult:
    """Run the study bundle in ``study_dir`` offline through the full DAG."""
    the_clock: Clock = clock if clock is not None else SystemClock()
    the_policy = policy if policy is not None else _load_policy()
    registry, config = _build_registry(study_dir, the_policy, montecarlo_replications)
    run_id = format_utc_seconds(the_clock.now()).replace(":", "").replace("-", "")
    fields = _manifest_fields(config, run_id)
    return Orchestrator(the_clock).run(
        study_dir / "runs" / run_id, registry, manifest_fields=fields
    )


def certification_rerun(
    run_dir: Path,
    *,
    clock: Clock | None = None,
    policy: Policy | None = None,
    montecarlo_replications: int | None = None,
) -> RunResult:
    """Re-execute a sealed certification run and assert byte-identity (NFR-101)."""
    the_clock: Clock = clock if clock is not None else SystemClock()
    the_policy = policy if policy is not None else _load_policy()
    study_dir = run_dir.parent.parent  # study/runs/<id>
    registry, _config = _build_registry(study_dir, the_policy, montecarlo_replications)
    target_id = format_utc_seconds(the_clock.now()).replace(":", "").replace("-", "")
    return Orchestrator(the_clock).rerun(
        run_dir, registry, target_run_dir=study_dir / "runs" / f"{target_id}-rerun"
    )


def _load_policy() -> Policy:
    return Policy.load(
        governance_dir() / _POLICY,
        mode="certification",
        playbook_path=playbooks_dir() / _PLAYBOOK,
    )
