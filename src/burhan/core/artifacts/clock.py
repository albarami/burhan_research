"""Injected clock protocol (standards §1: clocks injected, never ambient).

TC-01 components (results store, provenance, manifest) stamp timestamps only
through an injected ``Clock``. The production implementation arrives with the
orchestrator (M04); tests inject fixed clocks.
"""

from __future__ import annotations

import datetime as dt
from typing import Protocol


class Clock(Protocol):
    """Source of the current UTC time."""

    def now(self) -> dt.datetime:
        """Return a timezone-aware UTC datetime at whole-second precision."""
        ...
