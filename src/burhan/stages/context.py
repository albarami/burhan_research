"""Shared helpers for the TC-15 stage adapters.

Everything the adapters need beyond the certified module calls: the run-wide
compliance journal and decision log, provenance-recorded artifact writes, the
config/frame hand-off between stages (``StageContext`` carries neither), store-row
hygiene, and the two sample sizes the pipeline threads (raw N at power, analytical
N at achieved-power). Kept here so each adapter stays thin.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from burhan.core.artifacts.canonical import dumps
from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import ProvenanceActor, ProvenanceEventType, StudyConfig
from burhan.core.compliance import Compliance
from burhan.core.policy import DecisionLog

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path

    import pandas as pd  # type: ignore[import-untyped]

    from burhan.core.orchestrator import StageContext
    from burhan.core.playbook import Playbook

# Run-wide append-only records (each stage reopens and continues them).
COMPLIANCE_JOURNAL = "compliance_journal.jsonl"
COMPLIANCE_CHECKLIST = "METHOD_COMPLIANCE_CHECKLIST.md"
DECISION_LOG = "DECISION_LOG.jsonl"

# The cross-stage hand-off artifacts (StageContext carries no frame/config).
CONTRACT_CONFIG = "contract/study_config.json"
INGEST_SUMMARY = "ingest/ingest.json"
PREP_FRAME = "prep/frame.csv"
FRAME_INDEX = "case"

# The results store owns these three; a helper that embeds them for the
# jsonschema path (power/assumptions) must have them stripped before write.
_STORE_OWNED = ("schema_version", "created", "hash")


def compliance(ctx: StageContext, playbook: Playbook) -> Compliance:
    """Open the run-wide compliance tracker (replays prior stages' marks)."""
    return Compliance(playbook, ctx.store, ctx.run_dir / COMPLIANCE_JOURNAL, ctx.clock)


def decision_log(ctx: StageContext) -> DecisionLog:
    """Open the run-wide decision log (replays prior stages' entries)."""
    return DecisionLog(ctx.run_dir / DECISION_LOG, ctx.clock)


def _record_written(ctx: StageContext, relative: str) -> None:
    ctx.provenance.append(
        {
            "stage": ctx.stage,
            "actor": ProvenanceActor.WORKER.value,
            "event_type": ProvenanceEventType.ARTIFACT_WRITTEN.value,
            "trigger": f"{ctx.stage} produced an artifact",
            "effect": f"wrote {relative}",
        }
    )


def write_artifact(ctx: StageContext, relative: str, payload: object) -> Path:
    """Write a canonical-JSON artifact under the run dir and record it.

    Deterministic (canonical writer, injected clock); appends an
    ``artifact_written`` provenance entry naming the stage and path.
    """
    path = ctx.run_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(payload) + "\n", encoding="utf-8")
    _record_written(ctx, relative)
    return path


def write_config(ctx: StageContext, config: StudyConfig) -> Path:
    """Persist the contract's StudyConfig for downstream stages to reload."""
    return write_artifact(
        ctx, CONTRACT_CONFIG, config.model_dump(mode="json", by_alias=True, exclude_unset=True)
    )


def load_config(ctx: StageContext) -> StudyConfig:
    """Reload the StudyConfig the contract stage wrote (schema-revalidated)."""
    raw = json.loads((ctx.run_dir / CONTRACT_CONFIG).read_text(encoding="utf-8"))
    return validate_and_build(StudyConfig, raw)


def write_frame(ctx: StageContext, frame: pd.DataFrame) -> Path:
    """Persist the analytical frame as canonical CSV (deterministic, round-trips).

    ``\\n`` line terminator and default (shortest-round-trip) float formatting
    keep the bytes identical across reruns for the byte-identity assertion.
    """
    path = ctx.run_dir / PREP_FRAME
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, lineterminator="\n")
    _record_written(ctx, PREP_FRAME)
    return path


def load_frame(ctx: StageContext) -> pd.DataFrame:
    """Reload the analytical frame the prep stage wrote (``case`` index restored)."""
    import pandas as pd

    return pd.read_csv(ctx.run_dir / PREP_FRAME, index_col=FRAME_INDEX)


def raw_n(ctx: StageContext) -> int:
    """The raw sample size ingest recorded (a-priori power runs before prep)."""
    summary = json.loads((ctx.run_dir / INGEST_SUMMARY).read_text(encoding="utf-8"))
    return int(summary["raw_n"])


def analytical_n(ctx: StageContext) -> int:
    """The analytical N (post-screening rows in the persisted frame)."""
    return int(len(load_frame(ctx)))


def store_row(ctx: StageContext, fields: Mapping[str, object]) -> None:
    """Write one statistic row, stripping any store-owned fields a helper embeds.

    ``power_store_rows`` / ``assumptions_store_rows`` carry ``schema_version`` /
    ``created`` / ``hash`` for their jsonschema path; the store owns those and
    halts if handed them, so this drops them and lets the store re-inject.
    """
    ctx.store.write({key: value for key, value in fields.items() if key not in _STORE_OWNED})


def store_rows(ctx: StageContext, rows: Iterable[Mapping[str, object]]) -> None:
    """Write a sequence of statistic rows in order (see :func:`store_row`)."""
    for row in rows:
        store_row(ctx, row)
