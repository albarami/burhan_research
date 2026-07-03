"""Test bootstrap: make src/ and tests/golden importable (TC-01 PLAN v2 Fix 1)."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
for _path in (str(_ROOT / "src"), str(_ROOT / "tests" / "golden")):
    if _path not in sys.path:
        sys.path.insert(0, _path)
