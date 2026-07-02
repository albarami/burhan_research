"""Test bootstrap: make src/ importable (uv virtual project; TC-01 PLAN v2 Fix 1)."""

import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parents[3] / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
