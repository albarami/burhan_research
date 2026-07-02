"""Shared governance-test helpers: template copies with targeted mutations.

The governed templates in ``policy/`` are read-only; tests operate on
mutated copies written under tmp_path. Mutations are explicit callables so
each test names exactly what it changes.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[3]
POLICY_TEMPLATE = REPO / "policy" / "decision_policy.template.yaml"
REGISTRY_TEMPLATE = REPO / "policy" / "protected_decisions.registry.yaml"
PLAYBOOK = REPO / "playbooks" / "CB_SEM_PLAYBOOK_v1.0.yaml"

FIXED_NOW = dt.datetime(2026, 7, 2, 9, 0, 0, tzinfo=dt.UTC)


class FixedClock:
    def now(self) -> dt.datetime:
        return FIXED_NOW


def load_yaml(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def write_yaml(directory: Path, name: str, data: dict[str, Any]) -> Path:
    path = directory / name
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def policy_copy(
    directory: Path,
    *,
    status: str | None = None,
    mutate: Callable[[dict[str, Any]], None] | None = None,
) -> Path:
    data = load_yaml(POLICY_TEMPLATE)
    if status is not None:
        data["meta"]["status"] = status
    if mutate is not None:
        mutate(data)
    return write_yaml(directory, "decision_policy.yaml", data)


def registry_copy(
    directory: Path,
    *,
    status: str | None = None,
    mutate: Callable[[dict[str, Any]], None] | None = None,
) -> Path:
    data = load_yaml(REGISTRY_TEMPLATE)
    if status is not None:
        data["meta"]["status"] = status
    if mutate is not None:
        mutate(data)
    return write_yaml(directory, "protected_registry.yaml", data)


def playbook_copy(
    directory: Path, *, mutate: Callable[[dict[str, Any]], None] | None = None
) -> Path:
    data = load_yaml(PLAYBOOK)
    if mutate is not None:
        mutate(data)
    return write_yaml(directory, "playbook.yaml", data)
