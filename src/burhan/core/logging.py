"""Structured logging (standards §1: no ``print``; structured records only).

Records render as canonical JSON objects. Only explicitly passed structured
payloads (``extra={"data": ...}``) are serialized, and only if they satisfy
the canonical closed domain — a non-canonical payload raises loudly instead
of being coerced (NFR-201). Log metadata about raw data (counts, hashes,
column names), never respondent values (standards §7).

Timestamps are deliberately absent from this formatter: run-log timestamping
is orchestrator (M04) configuration with an injected clock; this module makes
no ambient clock calls (standards §1).
"""

from __future__ import annotations

import logging
from typing import Any

from burhan.core.artifacts.canonical import dumps

ROOT_LOGGER_NAME = "burhan"


class CanonicalJsonFormatter(logging.Formatter):
    """Render each record as one canonical JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        data = getattr(record, "data", None)
        if data is not None:
            payload["data"] = data
        return dumps(payload)


def get_logger(name: str) -> logging.Logger:
    """Return a logger namespaced under the ``burhan`` root.

    The root logger carries a ``NullHandler`` (library convention); handlers
    and formatters are attached by the orchestrator or by tests.
    """
    root = logging.getLogger(ROOT_LOGGER_NAME)
    if not any(isinstance(handler, logging.NullHandler) for handler in root.handlers):
        root.addHandler(logging.NullHandler())
    qualified = name if name.startswith(ROOT_LOGGER_NAME) else f"{ROOT_LOGGER_NAME}.{name}"
    return logging.getLogger(qualified)
