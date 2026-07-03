"""Benchmark bootstrap: make src/ importable (tests/conftest.py adds R_LIBS)."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SRC = str(_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
