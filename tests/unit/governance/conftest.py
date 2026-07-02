"""Test bootstrap: make src/ importable.

The project is a uv virtual project (uv.lock: source = { virtual = "." }),
so ``burhan`` is not installed into the environment. Same mechanism as
tests/unit/core (TC-01 PLAN v2 Fix 1), strictly inside deliverable paths.
"""

import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parents[3] / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
