"""Suite-wide bootstrap: R worker sessions see the renv project library.

The TC-04 harness asserts renv synchronization before any computation,
and since E-R3 the workers' packages (lavaan/semTools/simsem/psych) live
only in the renv project library. Worker sessions spawn from the repo
root without renv activation, so the project library must be on R_LIBS —
the same wiring CI exports since TC-08c. Computed once per session; a
missing Rscript leaves the environment untouched (non-R test runs).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]


def _project_r_libs() -> str | None:
    try:
        completed = subprocess.run(  # noqa: S603 — fixed argv, no shell
            ["Rscript", "-e", 'cat(renv::paths[["library"]](project = "workers/r"))'],
            capture_output=True,
            text=True,
            cwd=_REPO,
            timeout=120,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    path = completed.stdout.strip()
    return path or None


if "R_LIBS" not in os.environ:
    _libs = _project_r_libs()
    if _libs:
        os.environ["R_LIBS"] = _libs
