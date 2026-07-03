"""Test bootstrap: make src/, tests/golden, and this directory importable."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
for _path in (
    str(_ROOT / "src"),
    str(_ROOT / "tests" / "golden"),
    str(_ROOT / "tests" / "unit" / "stats_measurement"),
):
    if _path not in sys.path:
        sys.path.insert(0, _path)
