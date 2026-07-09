# TC-19 — PLAN v1: R worker renv activation context

| | |
|---|---|
| **Contract** | `docs/09_task_contracts/TC-19.md` (ISSUED) |
| **Branch** | `tc/tc-19-rworker-renv-context` |
| **Scope wall** | `src/burhan/core/rworker.py` + `tests/unit/orchestrator/test_rworker.py` **only** |
| **State** | PLAN v1 — **no implementation**; hold for review |

> **This plan authorizes no edits to** `workers/r/harness.R`, `workers/r/renv.lock`, `workers/r/renv/`, or any study-bundle file. The fix lives entirely in the Python worker-invocation seam and its unit tests.

---

## 1. Root cause (recap, from the approved diagnosis)

`RWorker.call()` spawns `subprocess.run(argv, …)` for `Rscript harness.R <worker.R> <in> <out>` with **no `cwd` and no `env`** (`rworker.py:107-109`). From the `burhan`/pytest process cwd (repo root, which has no `.Rprofile`), the `workers/r` project renv never activates, so `.libPaths()` stays on the **system** library and `harness.R:15` `renv::status(project = workers/r)` compares the `workers/r` lockfile against the wrong library → false `RENV_DRIFT` → NFR-102 `IntegrityHalt`. Five-context reproduction proved the `workers/r` renv project is itself **consistent** (synchronized when the project is active), so the fix is to run the subprocess **in the project context**, not to restore anything.

## 2. Implementation design (described here; applied only after PLAN approval)

Two edits to `src/burhan/core/rworker.py`, nothing else:

1. **`__init__` — normalize the worker dir to absolute** (path safety for a caller-injected relative dir; idempotent for the already-resolved default):
   ```python
   self._workers_dir = (
       workers_dir if workers_dir is not None else _default_workers_dir()
   ).resolve()
   ```
2. **`call()` — run the subprocess in the project context** (retain the existing `# noqa: S603`):
   ```python
   completed = subprocess.run(  # noqa: S603 — argv fixed above; no shell
       argv,
       cwd=self._workers_dir,
       capture_output=True,
       text=True,
       timeout=self._timeout,
       check=False,
   )
   ```

With `cwd=workers/r`, `Rscript` auto-sources `workers/r/.Rprofile → renv/activate.R`, which sets `RENV_PROJECT`/`.libPaths()` to the project library **before** `harness.R` runs its NFR-102 check — exactly how renv is designed to bootstrap. `harness.R` is unchanged; the NFR-102 guard is unchanged, only given the correct library context. All four `argv` path arguments (harness, worker, input, output) are already absolute (`self._workers_dir` resolved; input/output derive from the absolute `run_dir`), so the `cwd` change cannot misresolve them.

## 3. Acceptance tests → concrete tests, files, assertions

All tests live in **`tests/unit/orchestrator/test_rworker.py`** (existing file; `REPO = Path(__file__).resolve().parents[3]`). Hermetic tests reuse the existing fake-Rscript harness (`_FAKE_RSCRIPT` / `FAKE_MODE`, `worker`/`run_dir` fixtures). Real-R tests gate on the existing convention `@pytest.mark.skipif(shutil.which("Rscript") is None, …)` and use the lightweight **`echo_worker`** (357 B) — `harness.R` performs the renv check *before* sourcing the worker, so no heavy statistics run.

### AT-M19-1 — cwd set on `subprocess.run` (RED-first, hermetic)
`test_call_runs_subprocess_in_workers_dir_cwd` — monkeypatch `burhan.core.rworker.subprocess.run` with a capturing stub that records `kwargs["cwd"]` and `argv`, writes a valid output envelope, and returns `CompletedProcess(argv, 0, "", "")`. Drive it through `worker.call("echo_worker", {}, call_id=…, run_dir=…, seed=1)`. Assert:
- `captured["cwd"] == worker._workers_dir` (== `REPO/"workers"/"r"`);
- `Path(captured["cwd"]).is_absolute()`;
- every path arg is absolute: `all(Path(a).is_absolute() for a in captured["argv"][1:])`.
**RED pre-fix:** `cwd` kwarg absent → `captured["cwd"] is None` ≠ workers/r.

### AT-M19-2 — false drift reproduces without cwd, clears with cwd (real-R, skipif)
- `test_false_renv_drift_reproduces_without_project_cwd` *(guard/documentation — passes pre & post fix)*: write a minimal valid envelope, then call `subprocess.run(["Rscript", str(REPO/"workers/r/harness.R"), str(REPO/"workers/r/echo_worker.R"), in, out], cwd=tmp_path, capture_output=True, text=True)` where `tmp_path` has no `.Rprofile` (mirrors the pre-fix worker). Assert `returncode == 3` and `"RENV_DRIFT" in stderr`. Documents the exact failure the DBA run hit.
- `test_renv_drift_clears_with_project_cwd` *(RED-first → GREEN)*: `RWorker(rscript="Rscript", workers_dir=REPO/"workers"/"r").call("echo_worker", {"greeting": "burhan"}, call_id="c201", run_dir=run_dir, seed=424242)`. Assert it **returns a valid echo result** (renv gate passed → reached computation), e.g. `result["echo"] == {"greeting": "burhan"}` and `0.0 <= float(result["draw"]) <= 1.0`. **RED pre-fix:** RWorker sets no cwd → `RENV_DRIFT` → `IntegrityHalt`.
  - *Note:* the existing `test_real_r_echo_worker_round_trip` (test_rworker.py:143-157) is the same pre-existing real-R manifestation — no longer skipped now that R 4.5.2 is on PATH — and is expected to be **currently RED** for this exact reason; the fix turns it GREEN too. PLAN v1 does not modify it beyond confirming it goes green.

### AT-M19-3 — real drift still maps to IntegrityHalt (guard not weakened)
- `test_renv_drift_halts_named` *(EXISTING hermetic, test_rworker.py:101; retained + strengthened)*: `FAKE_MODE="drift"` → assert `IntegrityHalt`, `excinfo.value.message == "renv drift detected at worker startup (NFR-102)"`, `to_report()["details"]["stderr"]` contains `"RENV_DRIFT"`, `exit_code == 3`. Passes pre & post fix (the returncode→halt mapping is untouched by the cwd change).
- `test_real_renv_drift_still_halts_with_cwd` *(real-R, skipif; fix active)*: build a **throwaway** `tmp_workers/` containing a **copy** of `harness.R` (read-only copy, not an edit of the governed file), a trivial `echo_worker.R`, and a **synthetic unsatisfiable** `renv.lock` (JSON listing one bogus package). `RWorker(rscript="Rscript", workers_dir=tmp_workers).call(…)` runs with `cwd=tmp_workers` (fix active) → real `renv::status` returns not-synchronized → assert `IntegrityHalt` with `"RENV_DRIFT"` in the report. Proves genuine drift still halts **even with the cwd fix** and touches no governed renv file.

### AT-M19-4 — absolute path safety, default and injected (RED-first for injected, hermetic)
- `test_workers_dir_absolute_for_default`: `RWorker()._workers_dir.is_absolute()` is `True`.
- `test_workers_dir_absolute_for_injected_relative`: `w = RWorker(workers_dir=Path("workers/r"))` → `w._workers_dir.is_absolute()` and `w._workers_dir == (Path.cwd() / "workers/r").resolve()`. **RED pre-fix:** `__init__` stores the relative path unresolved. (AT-M19-1 additionally asserts the four `argv` paths are absolute.)

### AT-M19-5 — no artifact mutation; whole prior suite green
- `test_real_r_call_leaves_renv_lock_unchanged` *(real-R, skipif)*: capture `sha256(workers/r/renv.lock)` before and after a real `echo_worker` call through `RWorker`; assert equal (the worker only *reads* renv state).
- **Command:** `uv run pytest -q` → entire prior suite green, including the now-fixed real-R tests.
- **Review guards:** `git diff --stat main…` shows only `src/burhan/core/rworker.py` + `tests/unit/orchestrator/test_rworker.py`; `git status --porcelain` shows **nothing** under `workers/r/renv/`, `workers/r/renv.lock`, or `workers/r/harness.R`. The study bundle and DBA run artifacts live outside the repo (`~/research/burhan-studies/…`); tests use only `tmp_path` run dirs and never touch them.

| AT | Test(s) | Kind | RED-first? |
|----|---------|------|:--:|
| M19-1 | `test_call_runs_subprocess_in_workers_dir_cwd` | hermetic (monkeypatch) | ✅ |
| M19-2 | `…reproduces_without_project_cwd` (guard) · `…clears_with_project_cwd` | real-R skipif | 2nd ✅ |
| M19-3 | `test_renv_drift_halts_named` (existing) · `…real_renv_drift_still_halts_with_cwd` | hermetic + real-R | guard |
| M19-4 | `…absolute_for_default` · `…absolute_for_injected_relative` | hermetic | injected ✅ |
| M19-5 | `…leaves_renv_lock_unchanged` + full-suite + diff guards | real-R + review | guard |

## 4. Files touched (implementation phase)

- `src/burhan/core/rworker.py` — the two edits in §2.
- `tests/unit/orchestrator/test_rworker.py` — add AT-M19-1..5 tests; strengthen the existing `test_renv_drift_halts_named`; may extend the shared `_FAKE_RSCRIPT` only if a capturing stub isn't used (the monkeypatch stub in AT-M19-1 avoids touching it).

Nothing else. No governed doc, no R file, no lockfile, no study bundle.

## 5. Gates (standards §6; all green before completion report)

```bash
uv run ruff check . --no-cache && uv run ruff format --check .
uv run mypy src/
uv run pytest -q --cov=src --cov-report=term     # core/rworker.py ≥90% (standards §3; not in the 100% set)
uv run burhan doctor                             # environment untouched (post-commit, clean tree)
```
No R sources change, so `lintr` stays green (no-op). Env per the standing recipe (source `~/.config/burhan/.env` + pins) for `doctor`/real-R tests.

## 6. RED → GREEN execution order (implementation phase)

1. Write the RED-first tests (AT-M19-1, AT-M19-4 injected, AT-M19-2 clears-with-cwd); run the file → confirm each fails for the **stated** reason (no `cwd` kwarg / unresolved relative dir / `RENV_DRIFT` halt). Confirm the existing real-R round-trip is RED for the same cause.
2. Add the guard tests (AT-M19-2 reproduce, AT-M19-3 real-drift-tmp + strengthened hermetic, AT-M19-5 lock-hash); confirm the guards pass pre-fix (except the RED-first ones).
3. Apply the two edits in §2.
4. Run full gates → all GREEN; real-R tests now pass; guards still hold.
5. Completion report; await Codex verdict.

## 7. Risks / ripples

- **Existing real-R round-trip currently RED:** `test_real_r_echo_worker_round_trip` runs (not skipped) now that R is installed and hits this bug; the fix turns it green. Expected, not a regression introduced by TC-19.
- **`.resolve()` idempotence:** the `worker` fixture injects `REPO/"workers"/"r"` (already absolute), so normalization is a no-op there — no existing assertion should shift. Confirm at impl time.
- **Real-R tests need Rscript + the `workers/r` renv library present** (both present in the cert environment; the library is already consistent — **no restore**). They skip cleanly where R is absent (declared, not hidden).
- **Genuine-drift tmp test** needs `renv` loadable from a user/site library to call `renv::status` (confirmed available without activation in the diagnosis); guarded by skipif and asserted specifically on `RENV_DRIFT`/`IntegrityHalt`.

## 8. Definition of Done

AT-M19-1..5 green; whole prior suite green; gates clean; `# noqa: S603` retained; no edit outside the two scoped files. On Codex APPROVE + merge (standing order), re-run the exact Gate-1 command with the absolute `--reference` path — the run should proceed past `power` into prep (N-chain) → measurement → structural → effects → `REFERENCE_COMPARISON.md`.
