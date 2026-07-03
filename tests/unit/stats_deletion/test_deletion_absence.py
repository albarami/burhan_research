"""AT-M10-5 (absence): batch deletion has no code path (FR-706).

Enforcement is architectural, proven two ways: the module's public
surface exposes no callable that accepts multiple items to delete in
one step, and the source carries none of the batch-removal idioms.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import burhan.stats.deletion as deletion_module

REPO = Path(__file__).resolve().parents[3]
SOURCE = REPO / "src" / "burhan" / "stats" / "deletion.py"


def test_no_public_callable_accepts_an_item_collection() -> None:
    for name, member in vars(deletion_module).items():
        if name.startswith("_") or not inspect.isfunction(member):
            continue
        for param in inspect.signature(member).parameters.values():
            assert param.name not in {"items", "codes", "batch", "to_delete"}, (name, param.name)


def test_single_step_remover_takes_exactly_one_item() -> None:
    # The one primitive that shrinks a model takes a single item code —
    # a string — never an iterable of them.
    remover = deletion_module._without_item  # noqa: SLF001
    parameters = list(inspect.signature(remover).parameters.values())
    item_params = [p for p in parameters if p.name == "item"]
    assert len(item_params) == 1
    assert item_params[0].annotation == "str"


def test_source_carries_no_batch_removal_idiom() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    for token in ("batch", "bulk", "drop(columns", "difference("):
        assert token not in source, token
