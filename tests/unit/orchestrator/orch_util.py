"""Shared orchestrator-test helpers: stub stages, fixed clock, manifest fields."""

from __future__ import annotations

import datetime as dt
from typing import Any

from burhan.core.orchestrator import PIPELINE, Stage, StageContext

FIXED_NOW = dt.datetime(2026, 7, 2, 9, 0, 0, tzinfo=dt.UTC)


class FixedClock:
    def now(self) -> dt.datetime:
        return FIXED_NOW


class TickingClock:
    """Whole-second monotonic clock for lifecycle stamps."""

    def __init__(self) -> None:
        self._t = FIXED_NOW

    def now(self) -> dt.datetime:
        self._t += dt.timedelta(seconds=1)
        return self._t


class StubStage:
    """A minimal, deterministic stage writing one artifact per execution."""

    def __init__(self, name: str, action: Any = None) -> None:
        self.name = name
        self.consumes: tuple[str, ...] = ()
        self.produces: tuple[str, ...] = (f"{name}.txt",)
        self._action = action

    def execute(self, ctx: StageContext) -> None:
        if self._action is not None:
            self._action(ctx)
            return
        target = ctx.run_dir / f"{self.name}.txt"
        target.write_text(f"{self.name}: seed={ctx.stage_seed}\n", encoding="utf-8")


def stub_registry(overrides: dict[str, Any] | None = None) -> dict[str, Stage]:
    """A full stub registry covering the fixed DAG, with optional overrides."""
    registry: dict[str, Stage] = {name: StubStage(name) for name in PIPELINE}
    if overrides:
        registry.update(overrides)
    return registry


def manifest_fields() -> dict[str, Any]:
    return {
        "run_id": "20260702T090000Z",
        "study_id": "example-adoption-2026",
        "master_seed": 424242,
        "engine": {"version": "0.1.0", "git_commit": "abcdef1", "git_dirty": False},
        "hashes": {
            "study_config": "c" * 64,
            "decision_policy": "d" * 64,
            "protected_registry": "e" * 64,
            "playbook": "f" * 64,
            "prompts": {
                "node_a": {"version": "1.0", "sha256": "0" * 64},
                "node_b": {"version": "1.0", "sha256": "1" * 64},
                "node_c": {"version": "1.0", "sha256": "2" * 64},
            },
            "uv_lock": "3" * 64,
            "renv_lock": "4" * 64,
        },
        "environment": {
            "python": "3.12.13",
            "r": "4.4.1",
            "os": "WSL2",
            "doctor_passed": True,
        },
        "llm_nodes": {
            "node_a": {
                "provider": "anthropic",
                "model": "m",
                "lineage": "anthropic.claude",
                "temperature": 0,
            },
            "node_b": {
                "provider": "anthropic",
                "model": "m",
                "lineage": "anthropic.claude",
                "temperature": 0,
            },
            "node_c": {
                "provider": "openai",
                "model": "m",
                "lineage": "openai.gpt",
                "temperature": 0,
            },
        },
    }
