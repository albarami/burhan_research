"""Test bootstrap: make src/, this dir, and the orchestrator test-utils
importable to the TC-15 stage-adapter unit tests."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
for _path in (
    str(_ROOT / "src"),
    str(_ROOT / "tests" / "unit" / "stages"),
    str(_ROOT / "tests" / "unit" / "orchestrator"),
    str(_ROOT / "tests" / "unit" / "stats_deletion"),
    str(_ROOT / "tests" / "golden"),
    str(_ROOT / "tests" / "integration"),
    str(_ROOT / "tests" / "fixtures"),
):
    if _path not in sys.path:
        sys.path.insert(0, _path)
