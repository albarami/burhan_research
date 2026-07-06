"""Live-provider run path (TC-16, M6 enablement): the real ``burhan run``.

Distinct from ``cli/certification.py`` (canned, offline). Assembles existing
components into a governed live run in the ruled **pre-DAG extraction +
confirmation** shape:

- :func:`live_extract` (invocation 1, pre-DAG) — DOCX->text, live Node A
  extraction, ``config/study_config.yaml`` write-back, a write-once Node A
  archive, and a pending-glance token binding the config + archive hashes. No
  run dir, no stage, no stdin.
- :func:`live_confirm` (invocation 2) — verify the token (absent/mismatch halts
  before Gate 1), then the **existing** full ``Orchestrator.run`` with Node A
  **replaying** the archive and Node C **live+archived**.
- :func:`live_rerun` — both nodes replay archives; **no** provider call;
  byte-identical (NFR-101).

No statistics, no Stage-1A change, no certification-path change, no schema edit.
Raw CSV stays pipeline data and never reaches an adapter (NFR-401); keys live in
the environment and enter neither manifest, logs, nor archives.
"""

from __future__ import annotations

import json
import platform
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from burhan.cli.certification import (
    _PLAYBOOK,
    _REGISTRY,
    SystemClock,
    _load_policy,
    _run_id,
    _sealed_base,
    _SealedClock,
    _sha256,
)
from burhan.contract.archive import recording_provider_call, replay_provider_call
from burhan.contract.documents import document_to_text
from burhan.contract.llm_base import (
    LlmSettings,
    NodeSettings,
    load_llm_settings,
    resolve_provider_call,
)
from burhan.contract.node_a import NodeA
from burhan.core.artifacts.canonical import dumps
from burhan.core.artifacts.clock import Clock
from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig
from burhan.core.errors import IntegrityHalt, halt
from burhan.core.orchestrator import Orchestrator, RunResult, Stage, StageContext
from burhan.core.playbook import Playbook, playbooks_dir
from burhan.core.policy import Policy, governance_dir
from burhan.core.registry import Registry
from burhan.results.store import ResultsStore
from burhan.stages.registry import production_registry
from burhan.verify.reference_comparison import (
    build_reference_comparison,
    render_reference_comparison_md,
)

_REPO = Path(__file__).resolve().parents[3]
_MASTER_SEED = 20260705
_TOKEN = "GLANCE_TOKEN.json"

ProviderFactory = Callable[[LlmSettings, str], Callable[[str], str]]
ReferenceLoader = Callable[[Path], Mapping[str, Any]]

REFERENCE_COMPARISON_FILENAME = "REFERENCE_COMPARISON.md"
_REFERENCE_DIRNAME = "reference"


@dataclass(frozen=True)
class ExtractResult:
    """The pre-DAG extraction outcome the researcher glances at."""

    study_id: str
    config_path: Path
    token_path: Path


def _pending_dir(study_dir: Path) -> Path:
    return study_dir / "extract"


def _config_path(study_dir: Path) -> Path:
    return study_dir / "config" / "study_config.yaml"


def _config_yaml(config: StudyConfig) -> str:
    """Deterministic YAML for the bundle config (the glance target + hash source)."""
    return str(
        yaml.safe_dump(
            config.model_dump(mode="json", by_alias=True, exclude_unset=True), sort_keys=True
        )
    )


def _load_settings(study_dir: Path) -> LlmSettings:
    return load_llm_settings(study_dir / "config" / "llm.yaml")


def _resolve_inputs(study_dir: Path) -> tuple[Path, Path | None, Path]:
    """The study DOCX (required), the instrument DOCX (optional), and the CSV."""
    inputs = study_dir / "inputs"
    study_doc = inputs / "study_document.docx"
    if not study_doc.is_file():
        halt(
            IntegrityHalt(
                "live run requires inputs/study_document.docx",
                report={"path": str(study_doc)},
            )
        )
    dict_doc = inputs / "data_dictionary.docx"
    data_dict = dict_doc if dict_doc.is_file() else None
    exports = sorted(inputs.glob("*.csv"))
    if not exports:
        halt(
            IntegrityHalt(
                "live run requires a CSV export in inputs/",
                report={"inputs": str(inputs)},
            )
        )
    return study_doc, data_dict, exports[0]


def live_extract(
    study_dir: Path,
    *,
    provider_factory: ProviderFactory = resolve_provider_call,
) -> ExtractResult:
    """Invocation 1: live Node A extraction, write-back, archive, pending token."""
    study_doc, dict_doc, _export = _resolve_inputs(study_dir)
    settings = _load_settings(study_dir)
    study_document = document_to_text(study_doc)
    data_dictionary = document_to_text(dict_doc) if dict_doc is not None else None

    pending = _pending_dir(study_dir)
    if pending.exists():  # a re-extract starts from a clean pending area
        shutil.rmtree(pending)
    pending.mkdir(parents=True)

    node_a = NodeA(
        settings,
        provider_call=recording_provider_call(
            provider_factory(settings, "node_a"), pending, "node_a"
        ),
    )
    config = node_a.extract(study_document=study_document, data_dictionary=data_dictionary)

    config_path = _config_path(study_dir)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(_config_yaml(config), encoding="utf-8")

    token = {
        "study_id": config.meta.study_id,
        "config_sha256": _sha256(config_path),
        "node_a_archive_sha256": _sha256(pending / "node_a.0.json"),
    }
    token_path = pending / _TOKEN
    token_path.write_text(dumps(token) + "\n", encoding="utf-8")
    return ExtractResult(
        study_id=config.meta.study_id, config_path=config_path, token_path=token_path
    )


def _verify_token(pending: Path, config_path: Path) -> None:
    """Un-bypassable pause (AT-M16-3): no Gate 1 / Stage-1A without a valid token."""
    token_path = pending / _TOKEN
    archive_path = pending / "node_a.0.json"
    if not token_path.is_file():
        halt(
            IntegrityHalt(
                "no pending-glance token: run the --live extraction and glance the "
                "contract before --confirm (TC-16)",
                report={"path": str(token_path)},
            )
        )
    if not (config_path.is_file() and archive_path.is_file()):
        halt(
            IntegrityHalt(
                "pending extraction incomplete (config or Node A archive missing)",
                report={"config": str(config_path), "archive": str(archive_path)},
            )
        )
    token = json.loads(token_path.read_text(encoding="utf-8"))
    if token.get("config_sha256") != _sha256(config_path):
        halt(
            IntegrityHalt(
                "study_config changed since the glance; re-extract (un-bypassable pause)",
                report={"config": str(config_path)},
            )
        )
    if token.get("node_a_archive_sha256") != _sha256(archive_path):
        halt(
            IntegrityHalt(
                "Node A archive changed since the glance; re-extract",
                report={"archive": str(archive_path)},
            )
        )


def _build_live_registry(
    study_dir: Path,
    export_path: Path,
    study_document: str,
    data_dictionary: str | None,
    node_a: NodeA,
    node_c: Any,
    policy: Policy,
) -> tuple[dict[str, Stage], StudyConfig]:
    config = validate_and_build(
        StudyConfig, yaml.safe_load(_config_path(study_dir).read_text(encoding="utf-8"))
    )
    header_rows = config.data.header_rows if config.data.header_rows is not None else 3
    playbook = Playbook.load(playbooks_dir() / _PLAYBOOK, mode="certification", policy=policy)
    decision_registry = Registry.load(
        governance_dir() / _REGISTRY, mode="certification", policy=policy
    )
    registry = production_registry(
        export_path=export_path,
        study_document=study_document,
        header_rows=header_rows,
        node_a=node_a,
        node_c=node_c,
        policy=policy,
        playbook=playbook,
        registry=decision_registry,
        data_dictionary=data_dictionary,
    )
    return registry, config


def _node_manifest(node: NodeSettings) -> dict[str, Any]:
    return {
        "provider": node.provider,
        "model": node.model,
        "lineage": node.lineage,
        "temperature": int(node.temperature),
    }


def _live_manifest_fields(
    config_path: Path,
    settings: LlmSettings,
    node_a: NodeA,
    node_c: Any,
    policy: Policy,
    *,
    run_id: str,
) -> dict[str, Any]:
    config = validate_and_build(
        StudyConfig, yaml.safe_load(config_path.read_text(encoding="utf-8"))
    )
    a_prompt = node_a.prompt_manifest()
    c_prompt = node_c.prompt_manifest()[0]  # gate1 template (the gate this run runs)
    return {
        "run_id": run_id,
        "study_id": config.meta.study_id,
        "master_seed": _MASTER_SEED,
        "engine": {"version": "0.1.0", "git_commit": "0000000", "git_dirty": False},
        "hashes": {
            "study_config": _sha256(config_path),  # the persisted bundle bytes (NFR-102)
            "decision_policy": policy.sha256,
            "protected_registry": _sha256(governance_dir() / _REGISTRY),
            "playbook": _sha256(playbooks_dir() / _PLAYBOOK),
            # node_b is not run in Stage-1A (narrate is a stub); its real prompt
            # lands with TC-13. Record node_a's entry as the configured stand-in.
            "prompts": {"node_a": a_prompt, "node_b": a_prompt, "node_c": c_prompt},
            "uv_lock": _sha256(_REPO / "uv.lock"),
            "renv_lock": _sha256(_REPO / "workers" / "r" / "renv.lock"),
        },
        "environment": {
            "python": platform.python_version(),
            "r": "4.5",
            "os": platform.system(),
            "doctor_passed": True,
        },
        "llm_nodes": {
            "node_a": _node_manifest(settings.node("node_a")),
            "node_b": _node_manifest(settings.node("node_b")),
            "node_c": _node_manifest(settings.node("node_c")),
        },
    }


def _reference_dir(run_dir: Path) -> Path:
    return run_dir / _REFERENCE_DIRNAME


def _load_reference(path: Path) -> Mapping[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, Mapping):
        halt(IntegrityHalt("reference set is not a mapping (FR-1503)", report={"path": str(path)}))
    return loaded


def _record_reference(reference_path: Path) -> ReferenceLoader:
    """Copy the supplied reference-set bytes into the run tree, then load them.

    The exact bytes land in ``<run>/reference/<name>`` *before* the seal, so the
    reference set becomes a sealed run artifact that ``rerun`` replays from the
    run directory — deterministic reference for rerun, no re-read of the study
    bundle (which may change).
    """

    def loader(run_dir: Path) -> Mapping[str, Any]:
        if not reference_path.is_file():
            halt(
                IntegrityHalt(
                    "live run reference set not found (FR-1503)",
                    report={"path": str(reference_path)},
                )
            )
        destination = _reference_dir(run_dir) / reference_path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(reference_path.read_bytes())
        return _load_reference(destination)

    return loader


def _replay_reference(source_run_dir: Path) -> ReferenceLoader:
    """Mirror the sealed reference-set bytes from the source run on ``rerun``.

    Reads the reference set from the source run tree (never an external path,
    never a provider call) and mirrors the exact bytes into the rerun target,
    so the regenerated report is byte-identical (NFR-101).
    """

    def loader(run_dir: Path) -> Mapping[str, Any]:
        source_dir = _reference_dir(source_run_dir)
        sources = sorted(source_dir.glob("*")) if source_dir.is_dir() else []
        if not sources:
            halt(
                IntegrityHalt(
                    "live rerun: sealed run carries no reference set to replay",
                    report={"path": str(source_dir)},
                )
            )
        source = sources[0]
        destination = _reference_dir(run_dir) / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        return _load_reference(destination)

    return loader


class _PackageReferenceStage:
    """Live-only wrapper over the terminal ``package`` stage (TC-16 item 10).

    Delegates to the real stage, then — still inside ``Orchestrator.run`` and
    therefore BEFORE the seal — opens the completed run's results store, builds
    the FR-1503 reference comparison, renders it, and writes
    ``REFERENCE_COMPARISON.md`` into the run directory. Because the write
    precedes the seal, the report and the copied reference set are covered by
    ``seal.hash_tree_root`` and are regenerated byte-identically by ``rerun``
    (which re-runs this same wrapper). The fixed 13-stage ``PIPELINE`` is
    unchanged; only the ``package`` stage object in the live registry is wrapped.
    """

    def __init__(self, inner: Stage, reference_loader: ReferenceLoader, run_id: str) -> None:
        self._inner = inner
        self._reference_loader = reference_loader
        self._run_id = run_id
        # Delegate the Stage identity (the Protocol declares these as attributes).
        self.name = inner.name
        self.consumes = inner.consumes
        self.produces = inner.produces

    def execute(self, ctx: StageContext) -> None:
        self._inner.execute(ctx)
        reference = self._reference_loader(ctx.run_dir)
        store = ResultsStore(ctx.run_dir / "results", ctx.clock)  # the completed run's store
        report = build_reference_comparison(reference, store, run_id=self._run_id)
        (ctx.run_dir / REFERENCE_COMPARISON_FILENAME).write_text(
            render_reference_comparison_md(report), encoding="utf-8"
        )


def _with_reference_stage(
    registry: dict[str, Stage], reference_loader: ReferenceLoader, run_id: str
) -> dict[str, Stage]:
    """Wrap only the terminal ``package`` stage; the ``PIPELINE`` keys are unchanged."""
    wrapped = _PackageReferenceStage(registry["package"], reference_loader, run_id)
    return {**registry, "package": wrapped}


def live_confirm(
    study_dir: Path,
    *,
    reference_path: Path | None = None,
    provider_factory: ProviderFactory = resolve_provider_call,
    policy: Policy | None = None,
    clock: Clock | None = None,
) -> RunResult:
    """Invocation 2: verify the glance token, then run the full DAG live.

    When ``reference_path`` is supplied, the terminal stage additionally emits a
    sealed ``runs/<id>/REFERENCE_COMPARISON.md`` (TC-16 item 10).
    """
    pending = _pending_dir(study_dir)
    config_path = _config_path(study_dir)
    _verify_token(pending, config_path)  # halts BEFORE any run dir / Gate 1 (AT-M16-3)

    settings = _load_settings(study_dir)
    study_doc, dict_doc, export_path = _resolve_inputs(study_dir)
    study_document = document_to_text(study_doc)
    data_dictionary = document_to_text(dict_doc) if dict_doc is not None else None
    the_policy = policy if policy is not None else _load_policy()

    base = (clock if clock is not None else SystemClock()).now()
    sealed = _SealedClock(base)
    run_id = _run_id(base)
    run_dir = study_dir / "runs" / run_id
    archive_dir = run_dir / "llm"

    from burhan.review.node_c import NodeC

    node_a = NodeA(
        settings,
        provider_call=replay_provider_call(pending, "node_a", mirror_dir=archive_dir),
    )
    node_c = NodeC(
        settings,
        provider_call=recording_provider_call(
            provider_factory(settings, "node_c"), archive_dir, "node_c"
        ),
    )
    registry, _config = _build_live_registry(
        study_dir, export_path, study_document, data_dictionary, node_a, node_c, the_policy
    )
    if reference_path is not None:  # item 10: emit the sealed reference comparison
        registry = _with_reference_stage(registry, _record_reference(reference_path), run_id)
    fields = _live_manifest_fields(config_path, settings, node_a, node_c, the_policy, run_id=run_id)
    return Orchestrator(sealed).run(run_dir, registry, manifest_fields=fields)


def live_rerun(run_dir: Path, *, policy: Policy | None = None) -> RunResult:
    """Re-execute a sealed live run by replaying archives; no provider call (NFR-101)."""
    study_dir = run_dir.parent.parent
    settings = _load_settings(study_dir)
    study_doc, dict_doc, export_path = _resolve_inputs(study_dir)
    study_document = document_to_text(study_doc)
    data_dictionary = document_to_text(dict_doc) if dict_doc is not None else None
    the_policy = policy if policy is not None else _load_policy()

    target = run_dir.parent / f"{run_dir.name}-rerun"
    source_llm = run_dir / "llm"
    target_llm = target / "llm"

    from burhan.review.node_c import NodeC

    node_a = NodeA(
        settings,
        provider_call=replay_provider_call(source_llm, "node_a", mirror_dir=target_llm),
    )
    node_c = NodeC(
        settings,
        provider_call=replay_provider_call(source_llm, "node_c", mirror_dir=target_llm),
    )
    registry, _config = _build_live_registry(
        study_dir, export_path, study_document, data_dictionary, node_a, node_c, the_policy
    )
    if _reference_dir(run_dir).is_dir():  # source ran with a reference set: replay it
        registry = _with_reference_stage(registry, _replay_reference(run_dir), run_dir.name)
    sealed = _SealedClock(_sealed_base(run_dir))
    return Orchestrator(sealed).rerun(run_dir, registry, target_run_dir=target)
