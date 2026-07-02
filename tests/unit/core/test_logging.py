"""Structured logging tests (standards §1: no print, structured only).

Log records are diagnostics, not sealed artifacts; the formatter emits
canonical-ordered JSON and refuses non-canonical payloads loudly.
"""

from __future__ import annotations

import json
import logging as stdlib_logging
from typing import Any

import pytest

from burhan.core.errors import IntegrityHalt, halt, reset_halt_sink
from burhan.core.logging import CanonicalJsonFormatter, get_logger


def _record(msg: str, args: tuple[str, ...] = (), **extra: Any) -> stdlib_logging.LogRecord:
    record = stdlib_logging.LogRecord(
        name="burhan.test",
        level=stdlib_logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=args,
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_formatter_emits_canonical_json() -> None:
    out = CanonicalJsonFormatter().format(_record("stage %s done", ("prep",)))
    assert out == '{"level":"INFO","logger":"burhan.test","message":"stage prep done"}'


def test_formatter_serializes_structured_data_canonically() -> None:
    out = CanonicalJsonFormatter().format(_record("m", data={"b": 2, "a": 1}))
    assert out == '{"data":{"a":1,"b":2},"level":"INFO","logger":"burhan.test","message":"m"}'


def test_formatter_rejects_non_canonical_data_loudly() -> None:
    with pytest.raises(IntegrityHalt):
        CanonicalJsonFormatter().format(_record("m", data={"x": object()}))


def test_get_logger_namespaces_under_burhan_root() -> None:
    assert get_logger("prep").name == "burhan.prep"
    assert get_logger("burhan.core").name == "burhan.core"
    root = stdlib_logging.getLogger("burhan")
    assert any(isinstance(h, stdlib_logging.NullHandler) for h in root.handlers)


class _ListHandler(stdlib_logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[stdlib_logging.LogRecord] = []

    def emit(self, record: stdlib_logging.LogRecord) -> None:
        self.records.append(record)


def test_default_halt_sink_logs_report_before_propagation() -> None:
    # The errors module's default sink emits via core.logging (PLAN v2 Fix 5).
    reset_halt_sink()
    handler = _ListHandler()
    logger = stdlib_logging.getLogger("burhan.halt")
    logger.addHandler(handler)
    try:
        exc = IntegrityHalt("boom", report={"k": 1})
        with pytest.raises(IntegrityHalt):
            halt(exc)
        assert len(handler.records) == 1
        assert handler.records[0].data == exc.to_report()  # type: ignore[attr-defined]
        rendered = CanonicalJsonFormatter().format(handler.records[0])
        assert json.loads(rendered)["data"] == exc.to_report()
    finally:
        logger.removeHandler(handler)
