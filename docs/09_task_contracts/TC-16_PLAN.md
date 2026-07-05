# TC-16 — PLAN v1 (live-run execution path, M6 enablement)

> **For the reviewer:** PLAN v1 only — no implementation. Per the issuance
> instruction, this plan maps AT-M16-1..8 to concrete tests and names the exact
> files, **and** surfaces open questions / contract conflicts. One genuine
> conflict was found (§4 Q-A). Per the standing rule ("if any are found, STOP
> rather than proposing implementation around them"), this plan **STOPS** on the
> run-model design and does **not** propose an implementation for the paused
> run; it requests a ruling. The tractable parts are mapped so the ruling has
> full context.

**Contract:** TC-16 (ISSUED @ `ea46606`). **Branch:** `tc/tc-16-live-run`.
**Deliverable:** live-provider `burhan run` assembled over existing components.
**Read first (done):** CLAUDE.md; TC-16.md; `docs/03_ARCHITECTURE.md` §4/§5/§9/§11;
`src/burhan/core/orchestrator.py`; `src/burhan/cli/certification.py`;
`src/burhan/stages/registry.py`; `src/burhan/stages/stage_1a.py` (Contract/Gate1);
`src/burhan/contract/llm_base.py`; `src/burhan/contract/node_a.py` (surface).

## 1. Scope walls (restated — these are invariants of every task below)

- No new statistics; no Stage-1A statistical drift (adapters/orchestration only).
- Certification stays canned/offline — unchanged and proven by test.
- Raw CSV never reaches an LLM (existing allowlist enforced on the live path).
- Pause-before-Gate-1 un-bypassable.
- Live LLM calls archived; rerun replays archives (NFR-101).
- Secrets never enter manifests, logs, or committed files.

## 2. Read-first component map (reuse — do not rebuild)

Everything TC-16 lists as "existing components" was verified present:

| Capability | Exists at | Reuse / build |
|---|---|---|
| Full-DAG run, seal, terminal states | `core/orchestrator.py:112-193` (`run`) | **reuse** |
| Full re-exec + byte-identity assertion | `core/orchestrator.py:195-241` (`rerun`) | **reuse** |
| Node A extraction (documents→config) | `stages/stage_1a.py:206-210` (Contract) → `contract/node_a.py:61` (`NodeA.extract`) | **reuse** |
| Node C Gate 1 audit | `stages/stage_1a.py:224-236` (Gate1) → `review/node_c.py` (`gate1`) | **reuse** |
| Registry wiring (nodes injected) | `stages/registry.py:41-80` (`production_registry`) | **reuse** |
| Real provider clients (network edge) | `contract/llm_base.py:249-292` (`resolve_provider_call`) | **reuse** |
| Real `llm.yaml` load + lineage check | `contract/llm_base.py:71-161` (`load_llm_settings`) | **reuse** |
| Raw-data boundary rejection (NFR-401) | `contract/llm_base.py:164-203` (`screen_boundary_input`) | **reuse** |
| Canned offline path to parallel | `cli/certification.py` (`certification_run`/`_build_registry`) | **parallel, don't touch** |
| Manifest hashes + seal | `core/manifest.py` | **reuse + extend fields** |
| Provenance (sanad) log | `core/provenance.py` | **reuse** |
| Reference-comparison builder (TC-12) | `verify/reference_comparison.py` | **reuse** (M6 step; entrypoint to confirm at impl) |

**To build (assembly + I/O only):** a DOCX→text util; a live-run orchestration
module (parallel to `cli/certification.py`); an LLM archive/replay layer; CLI
routing for the live path; manifest-field extensions. **None of these adds
statistics or governance.**

## 3. DOCX→text ingestion design (AT-M16-7)

- **New:** `src/burhan/contract/documents.py` — `document_to_text(path: Path) -> str`
  using `python-docx` (locked: `pyproject.toml`, `uv.lock`). Extracts paragraph +
  table text in document order; returns a single string.
- The study DOCX → `study_document` text; the survey-instrument DOCX →
  `data_dictionary` text. Both are the **text** inputs `NodeA.extract` already
  accepts (`node_a.py:61`); they pass through `screen_boundary_input` unchanged.
- **Halt behaviour:** a corrupt/unreadable DOCX raises a typed `IntegrityHalt`
  (never silently empty) — `screen_boundary_input` already rejects non-text, and
  the util raises before returning empty.
- **Raw CSV is NOT a document** — it stays ordinary pipeline data read by the
  `Ingest`/`Prep` stages (`stage_1a.py:180-189`); it is never handed to
  `document_to_text` and never to an adapter.

## 4. Open questions & contract conflicts — **STOP HERE**

### Q-A (CONTRACT CONFLICT — blocks the run-model): the un-bypassable pause vs. the orchestrator's governed invariants

**Finding.** `Contract` (Node A) and `Gate1` (Node C) are **adjacent stages inside
the single monolithic `Orchestrator.run` loop** (`registry.py:63-64`;
`orchestrator.py:131-187`). TC-16 item 5 + AT-M16-3 require the run to **halt after
Node A extraction/write-back and refuse to reach Gate 1 without an explicit
researcher confirmation token**. But the orchestrator, by governed design:

- "**exposes no input channel: nothing here reads stdin, ever (FR-306/FR-1401 —
  proven by the closed-stdin acceptance test)**" — `orchestrator.py:12-13`
  (test: `tests/unit/orchestrator/test_state_machine.py`);
- performs **no partial resume** — AD-03 (`03_ARCHITECTURE.md:21`): "resume logic
  is the enemy of bit-identical reproducibility (NFR-101)";
- `rerun` re-executes the **full** DAG and asserts byte-identity of every artifact
  (`orchestrator.py:195-241`, NFR-101).

An in-DAG pause between `contract` and `gate1` therefore **contradicts FR-306/FR-1401
(no input channel) and AD-03 (no partial resume)**, and the resolution changes the
governed run-state model (`03_ARCHITECTURE.md:81-101` fixes contract=S1, gate1=G1
as consecutive DAG stages with states `PENDING→RUNNING→COMPLETED`).

**Why I am stopping.** Making the pause work requires a run-model decision that
edits or reinterprets governed invariants — e.g. splitting the live run into two
orchestrated invocations (extract-phase halting at a **new** boundary state, then
a separate confirm-invocation), or moving live extraction to a pre-DAG step. Each
choice has different consequences for: the fixed DAG (arch §4), the run-state
enum, the seal/manifest, and how `rerun` (full re-exec) preserves byte-identity
across a paused→resumed run. **This is a governed-architecture decision, not an
implementer choice.** Picking one and writing tasks around it would violate the
scope wall and the standing "STOP, don't plan around conflicts" rule. **I need a
ruling before designing or implementing the paused run path.**

*(Decision surface for the ruling — stated, not chosen: does the pause resolve as
(i) a two-invocation extract→confirm run with a new terminal state, (ii) a pre-DAG
extraction step feeding an unchanged full-DAG run, or (iii) a governed change to
the orchestrator's input/resume invariants? Each needs a governed-doc position on
FR-306/AD-03/NFR-101 and the run-state model.)*

### Q-B (depends on Q-A): rerun replay shape

Archival/replay (§5) is designable at the mechanism level, but whether `rerun`
replays **one** sealed run or **two** phases depends entirely on Q-A's run-model.
Blocked until Q-A is ruled.

### Q-C (needs confirmation): study_config write-back target

Certification seeds Node A's echo by reading `study_dir/config/study_config.yaml`
(`certification.py:158`); the live path has **no** pre-existing config — Node A
produces it. TC-16 item 4 says "persist into the bundle's `config/`". Confirm:
write-back target = `$BURHAN_STUDIES_DIR/<study>/config/study_config.yaml`
(engine-external, FR-1402), and the manifest hashes the **produced** bytes
(`hashes.study_config`). Interacts with Q-A (when write-back happens relative to
the pause).

### Q-D / Q-E (design detail, resolvable — not blockers): `llm.yaml` staging location + which model IDs govern the live M6 run (manifest records model IDs, never keys); `data_dictionary` DOCX selection when multiple DOCX are staged.

## 5. Archival & replay mechanism (NFR-101) — mechanism explicit; final shape pending Q-A/Q-B

**Mechanism (independent of the pause):** on a **live** run, each adapter
`provider_call` is wrapped to (1) call the real client
(`resolve_provider_call`, `llm_base.py:249-292`), (2) write the exact
prompt+response to a write-once archive inside the sealed run dir
(e.g. `runs/<id>/llm/<node>.<seq>.json`). On **rerun**, the registry is rebuilt
(as `certification_rerun` already rebuilds it, `certification.py:209-227`) with a
**replay** `provider_call` that reads `<node>.<seq>.json` and returns the archived
response — **no network**. Because the archive is written once and replayed
verbatim, the regenerated archive is byte-identical and the existing
`rerun` identity assertion (`orchestrator.py:224-240`) holds. A planted archive
mismatch is caught by that same assertion (AT-M16-5). Keys never enter the archive
or manifest (only prompt/response text + model IDs).

**Blocked aspect:** if Q-A yields a two-phase run, "the sealed run dir" and "what
rerun replays" span two invocations — that boundary must be defined first.

## 6. AT-M16 → test/file mapping

**Tractable now (independent of Q-A):**

| AT | Test (new unless noted) | Files under test |
|---|---|---|
| AT-M16-2 (certification unchanged) | `tests/integration/test_it6_cli_certification.py` (existing, stays green) + new assertion that `certification_run` still injects canned `lambda` nodes & no network | `cli/certification.py` (unchanged) |
| AT-M16-4 (no raw data to LLM) | new `tests/unit/contract/test_live_boundary.py` — CSV path/bytes/dataframe rejected on the live `provider_call` path | `contract/llm_base.py` (reuse), live module |
| AT-M16-7 (DOCX ingestion) | new `tests/unit/contract/test_documents.py` — DOCX→text yields Node A input; corrupt DOCX → typed halt | `contract/documents.py` (new) |
| AT-M16-8 (no Stage-1A drift) | whole existing unit+golden+benchmark+integration suite stays green (CI) | none changed in `stats/`/`prep/`/`verify/` |

**Blocked pending Q-A ruling (run-model dependent):**

| AT | Why blocked |
|---|---|
| AT-M16-1 (live path real, drives to COMPLETED) | the end-to-end path includes the pause; its shape is Q-A |
| AT-M16-3 (pause un-bypassable) | **is** the Q-A conflict |
| AT-M16-5 (rerun replay identity) | replay span depends on Q-A/Q-B run-model |
| AT-M16-6 (write-back + manifest) | write-back timing relative to the pause is Q-A/Q-C |

**Proposed new files (shape confirmed only after Q-A):** `cli/live.py` (live_run /
live_rerun orchestration, parallel to `cli/certification.py`); archive/replay
helper (module TBD by Q-A); `cli/__init__.py` `run` routing (currently refuses at
`cli/__init__.py:41-45`); manifest-field extension for archive + `llm.yaml` model
IDs.

## 7. Muhasabah self-audit

- **Provenance:** every "exists" claim cites `file:line`; the one unread interface
  (`verify/reference_comparison.py` entrypoint) is flagged "to confirm", not asserted.
- **Assumptions:** Q-A's contradiction is inference from `orchestrator.py:12-13` +
  `registry.py:63-64` + AD-03 — labelled as the finding, with sources.
- **Fabrication:** no run was executed; no data read; no run-model chosen.
- **Requirements:** maps AT-M16-1..8, names files, states walls, includes DOCX and
  archival/replay designs, surfaces open questions — and STOPS on the conflict
  rather than planning around it, as instructed.
- **Reversibility:** this is a plan doc; the STOP prevents premature `src/` work.
- **Gate verdict: PASS** — with the explicit STOP on Q-A.

## 8. Requested ruling (before PLAN v2 / any implementation)

A governed position on **Q-A** (the pause vs. FR-306/FR-1401/AD-03/NFR-101 and the
run-state model), which unblocks Q-B/Q-C. Q-D/Q-E can be answered alongside or at
implementation. On the ruling I produce PLAN v2 (task-level TDD for AT-M16-1..8) or,
if Q-A needs a governed-doc change, escalate per change control first. **Holding —
no implementation.**
