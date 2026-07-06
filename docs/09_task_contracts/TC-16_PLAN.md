# TC-16 — PLAN v2 (live-run execution path, M6 enablement)

> **PLAN v2 — supersedes v1 (`7593c0a`) per the reviewer ruling on Q-A.** No
> implementation. v1 STOPPED on the pause/orchestrator question; the ruling
> resolved it: architecture permits interactive input **before/at G1**
> (`03_ARCHITECTURE.md:103` — "interactive input is possible only before/at G1
> (optional contract glance); from G1-pass to terminal state the orchestrator
> exposes no input channel"). The real constraints are **no stdin, no in-DAG
> human input, no partial resume**. This plan adopts the ruled **pre-DAG
> extraction + confirmation** model, maps AT-M16-1..8 fully (none blocked), and
> names the reference-comparison entrypoint exactly.

**Contract:** TC-16 (ISSUED @ `ea46606`). **Branch:** `tc/tc-16-live-run`.

## 1. The run model (per ruling)

Two CLI invocations, no shared/partial run, no new terminal state:

- **Invocation 1 — `burhan run <study> --live` (extract, pre-DAG).** DOCX→text →
  live Node A extraction → write `config/study_config.yaml` into the bundle →
  archive Node A prompt+response → write a **pending-glance token** binding the
  config hash + Node A archive hash. Not an `Orchestrator.run`: no run dir, no
  stage, no stdin, exits informationally. The researcher then glances at
  `config/study_config.yaml`.
- **Invocation 2 — `burhan run <study> --live --confirm` (confirmed run).** Verify
  the token against the *current* config + archive hashes (absent/mismatch →
  `IntegrityHalt`, **no Gate 1, no Stage-1A**). Then run the **existing full
  `Orchestrator.run`** over the production registry, with **Node A = replay of the
  archive** and **Node C = live+archived**. COMPLETED via the existing states.
- **`burhan rerun <run-dir> --live`.** Rebuild the registry with **both** nodes as
  replay (read run-dir archives); **no provider calls**; `Orchestrator.rerun`
  asserts byte-identity (NFR-101).

## 2. Pending-glance artifact/token location (reviewer's explicit question)

**Decision: a separate write-once pending area — NOT inside the eventual run
directory.** Reasoning, tied to the invariants:

- Invocation 1 is pre-DAG and creates **no** run dir (the run dir is created and
  **sealed by invocation 2's single `Orchestrator.run`**). Putting inv-1 outputs
  in the run dir and continuing in inv-2 would be **partial resume (AD-03)** and
  would split the seal across two invocations — both forbidden.
- Pending area: `$BURHAN_STUDIES_DIR/<study>/extract/` (write-once) holding the
  **Node A archive** (`node_a.0.json`) and **`GLANCE_TOKEN.json`**
  (`{study_id, config_sha256, node_a_archive_sha256, extracted_at}`).
  `config/study_config.yaml` is written to the bundle `config/` (the glance target).
- At **confirm**, invocation 2 **copies** the Node A archive into
  `runs/<id>/llm/node_a.0.json` so it is a run-dir artifact — hashed into the seal
  hash-tree (`manifest.py:59-82`) and compared by `rerun` (`orchestrator.py:224-240`).
- **Preserves:** manifest sealing (one `Orchestrator.run` owns the run dir),
  archive hashing (archive lives in the run dir → in `seal.hash_tree_root`), rerun
  identity (rerun reads the run dir only; the pending area is transient
  scaffolding it never touches).
- The token binds the config + archive hashes, so the run reproduces **exactly**
  what was glanced; a post-glance edit to `config/study_config.yaml` changes its
  hash → token invalid → refuse (the glance is read-only; changes require
  re-extraction). Un-bypassable (AT-M16-3).

## 3. Read-first component map (reuse — sourced)

| Capability | Exists at | Use |
|---|---|---|
| Full-DAG run/seal/states | `core/orchestrator.py:112-193` | reuse (invocation 2) |
| Full re-exec + byte-identity | `core/orchestrator.py:195-241` | reuse (rerun) |
| Deterministic sealed clock | `cli/certification.py:48-68` (`_SealedClock`) | reuse (live run + rerun) |
| Node A extract (YAML resp → StudyConfig, V-checks) | `contract/node_a.py:61-108`; `stages/stage_1a.py:206-210` | reuse |
| Node C Gate 1 | `stages/stage_1a.py:224-236`; `review/node_c.py` | reuse |
| Registry (nodes injected) | `stages/registry.py:41-80` | reuse |
| Real clients / settings / boundary | `contract/llm_base.py:249-292`, `:71-161`, `:164-203` | reuse |
| Manifest seal = whole-tree hash | `core/manifest.py:59-82,130-146` | reuse (archives hashed by seal) |
| Reference-comparison builder | `verify/reference_comparison.py:38` (`build_reference_comparison`) | reuse |
| Canned offline path (parallel, untouched) | `cli/certification.py` | do not modify |

**Build (assembly/plumbing only):** `contract/documents.py` (DOCX→text);
`contract/archive.py` (record/replay `provider_call` + archive read/write);
`cli/live.py` (`live_extract` / `live_confirm` / `live_rerun`); `cli/__init__.py`
routing; `render_reference_comparison_md` in `verify/reference_comparison.py`.
**No** statistics, **no** certification change, **no** governed-doc/schema edit.

## 4. DOCX→text ingestion (AT-M16-7)

`contract/documents.py`: `document_to_text(path: Path) -> str` via `python-docx`
(locked). Paragraphs + table cells in document order → one string. The study DOCX
→ `study_document`; the instrument DOCX → `data_dictionary`. A corrupt/unreadable
DOCX raises typed `IntegrityHalt` (never silently empty). The raw CSV is **not** a
document — it is read only by `Ingest`/`Prep` (`stage_1a.py:180-189`) and by
`validate_contract` (path, deterministic); it never reaches `document_to_text` or
an adapter.

## 5. Archive & replay (AT-M16-5, NFR-101)

`contract/archive.py`:
- `recording_provider_call(inner, archive_dir, node, seq) -> Callable[[str],str]` —
  wraps a real `resolve_provider_call`; on call, invokes `inner(prompt)`, writes
  write-once `{"prompt":…, "response":…}` to `archive_dir/<node>.<seq>.json`,
  returns the response.
- `replay_provider_call(archive_dir, node, seq) -> Callable[[str],str]` — returns
  the archived `response`; **never** calls a provider; a missing/mismatched archive
  → typed halt (caught by the rerun identity assertion for AT-M16-5's planted
  mismatch).
- Archive content is prompt+response **text** and model IDs only — **no keys**.
Because archives are run-dir artifacts written once and replayed verbatim, the
regenerated tree is byte-identical and `seal.hash_tree_root` matches on rerun.

## 6. Manifest & hashing (AT-M16-6) — no schema change

The manifest schema is closed (`additionalProperties:false`), and TC-16 forbids
governed edits — so we use **existing** slots:
- `hashes.study_config` = sha256 of the persisted `config/study_config.yaml`
  (existing field; set as `certification.py:198-204` already does).
- `llm_nodes.node_a/b/c.model` = real `llm.yaml` model IDs (existing fields).
- **Archived responses** are hashed into the manifest **via the seal hash-tree**
  (`manifest.py:59-82`) — they are run-dir files, so no dedicated `hashes.*` key
  (and no schema change) is needed. Keys appear in neither manifest, logs, nor
  archives.

## 7. Reference comparison (TC-16 item 10) — exact names

- **Builder (exists, reuse):** `build_reference_comparison(reference, store, *,
  run_id) -> dict` at `verify/reference_comparison.py:38`; test
  `tests/unit/verify/test_reference_comparison.py`. Emits the schema-valid
  `ReferenceComparisonReport` **JSON** (status/classification per the §3.1
  tolerances; domains = `ComparisonDomain`, `models.py:588-604`).
- **Renderer (new, item 10):** `render_reference_comparison_md(report: Mapping) ->
  str` added to `verify/reference_comparison.py` — pure markdown projection of the
  report (summary + per-comparison rows), **no statistics**. `live_confirm` writes
  it to `runs/<id>/REFERENCE_COMPARISON.md` when a reference set is supplied.
- **New test:** `tests/unit/verify/test_reference_comparison.py::
  test_render_reference_comparison_md` — asserts the md contains the summary
  counts and one row per comparison, and is a pure function of the report.
  (Item 10 has no binding AT-M16; it is exercised end-to-end during M6.)

## 8. AT-M16-1..8 — full mapping (TDD; none blocked)

| AT | Test (RED→GREEN) | Files under test |
|---|---|---|
| **AT-M16-1** live path real | `tests/integration/test_it7_live_run.py::test_live_extract_then_confirm_reaches_completed` — fixture study (tiny DOCX+CSV) + a **recording non-canned** provider stub; inv1 drives DOCX→NodeA(stub records)→config+archive+token, inv2 replays NodeA + Node C(stub records)→full DAG→COMPLETED; assert the stub **was invoked** (not the canned echo) | `cli/live.py`, `contract/documents.py`, `contract/archive.py`, `cli/__init__.py` |
| **AT-M16-2** cert unchanged | existing `tests/integration/test_it6_cli_certification.py` stays green + `tests/unit/cli/test_certification_canned.py::test_certification_still_canned_no_network` (asserts `certification_run` injects `lambda` nodes, no client) | `cli/certification.py` (unchanged) |
| **AT-M16-3** pause un-bypassable | `test_it7_live_run.py::test_confirm_without_token_halts_before_gate1` and `::test_confirm_with_tampered_config_halts` — no token / hash mismatch ⇒ `IntegrityHalt`, **no run dir, no Node C call, no stage executed** | `cli/live.py` (token check) |
| **AT-M16-4** no raw data to LLM | `tests/unit/contract/test_live_boundary.py::test_csv_never_reaches_adapter` — CSV path/bytes/dataframe rejected by `screen_boundary_input` on the live path; `export_path` goes to `validate_contract`, never to `provider_call` | `contract/llm_base.py` (reuse), `cli/live.py` |
| **AT-M16-5** rerun replay identity | `test_it7_live_run.py::test_rerun_replays_archives_byte_identical` (provider stub **raises if called**; artifacts byte-identical) + `::test_planted_archive_mismatch_is_caught` | `cli/live.py` (`live_rerun`), `contract/archive.py` |
| **AT-M16-6** write-back + manifest | `test_it7_live_run.py::test_writeback_and_manifest_hashes` — `hashes.study_config` = persisted config sha; `llm_nodes.*.model` = llm.yaml model IDs; archives in `seal.hash_tree_root`; **no key** in manifest/logs | `cli/live.py`, `core/manifest.py` (reuse) |
| **AT-M16-7** DOCX ingestion | `tests/unit/contract/test_documents.py::test_docx_to_text` and `::test_corrupt_docx_halts_typed` | `contract/documents.py` |
| **AT-M16-8** no Stage-1A drift | whole prior unit+golden+benchmark+integration suite green in CI; grep-assert no diff under `stats/`,`prep/`,`verify/` stat modules | none in Stage-1A modules |

**Fixtures:** `tests/integration/live_fixture/` — a tiny valid DOCX (built with
`python-docx` in a fixture helper), a 3-row CSV, a fixture `llm.yaml`, and a
recording/replay provider stub returning a fixed valid Node A YAML + Node C
`approve`. The stub is **non-canned** (records calls, distinct from
`certification_run`'s lambdas) so AT-M16-1 proves the live wiring.

## 9. File-by-file change list

**Create:** `src/burhan/contract/documents.py`; `src/burhan/contract/archive.py`;
`src/burhan/cli/live.py`; tests `test_it7_live_run.py`, `test_documents.py`,
`test_live_boundary.py`, `test_certification_canned.py`, `test_archive.py`,
`live_fixture/` helpers.
**Modify:** `src/burhan/cli/__init__.py` (`run` routes `--live`/`--live --confirm`
to `live_extract`/`live_confirm`; `rerun` routes `--live` to `live_rerun`;
non-`--live`/non-`--certification` still refuses); `verify/reference_comparison.py`
(+`render_reference_comparison_md`); `tests/unit/verify/test_reference_comparison.py`
(+md test).
**Untouched (walls):** all of `stats/`, `prep/`, `verify/` stat logic,
`stages/stage_1a.py` internals, `cli/certification.py`, every schema, playbook,
policy, registry.

## 10. TDD order (one PR, standards §6)

1. `documents.py` (AT-M16-7) · 2. `archive.py` (record/replay unit) · 3.
`test_live_boundary` (AT-M16-4) · 4. `live_extract` + token (AT-M16-1 inv1, -3) ·
5. `live_confirm` replay+live-C (AT-M16-1 inv2, -6) · 6. `live_rerun` (AT-M16-5) ·
7. cert-canned guard (AT-M16-2) · 8. reference md renderer (item 10) · 9. whole
suite + CI (AT-M16-8). Each step: failing test first, minimal code, gates green.

## 11. Muhasabah self-audit

- **Provenance:** every reuse point cites `file:line`; the ruling cites
  `03_ARCHITECTURE.md:103`; the manifest/seal claim cites `manifest.py:59-82`.
- **Assumptions:** archive = raw Node A YAML response (`node_a.py:70-80`), replayed
  verbatim — stated, sourced.
- **Fabrication:** none — no run executed, no data read; the reference-comparison
  entrypoint is named from the file, and the missing `.md` renderer is called out
  as new (not asserted to exist).
- **Requirements:** all AT-M16-1..8 mapped with files+tests, **none blocked**; the
  pending-area question answered; DOCX and archive/replay designs explicit;
  reference-comparison function+test named. No scope creep (no stats, no cert
  change, no governed edit).
- **Walls:** no stdin, no in-DAG input, no partial resume, raw CSV never to an LLM,
  pause un-bypassable, rerun replays archives, secrets never in
  manifest/logs/commits — each mapped to a test above.
- **Gate verdict: PASS.**

## 12. Hold

PLAN v2 complete. **Pausing for review — no implementation.** On approval I
implement test-first in the §10 order on `tc/tc-16-live-run`, gates green per
commit, then submit for the TC-16 verdict. M6 stays held until TC-16 is APPROVED,
merged, ledger-recorded, and CI-green.
