"""Test bootstrap: make src/, tests/fixtures/, tests/golden/, and this
directory importable to the TC-15 integration harness."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _path in (
    str(_ROOT / "src"),
    str(_ROOT / "tests" / "fixtures"),
    str(_ROOT / "tests" / "golden"),
    str(_ROOT / "tests" / "integration"),
    str(_ROOT / "tests" / "unit" / "orchestrator"),
):
    if _path not in sys.path:
        sys.path.insert(0, _path)
