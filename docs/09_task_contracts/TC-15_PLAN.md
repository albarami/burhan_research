# TC-15 — PLAN v1 (pipeline-integration; M5 C4 remediation)

> **Status:** PLAN v1 — submitted for Codex review **before** implementation (per issuance order step 2). No `src/` code written yet. Contains open decisions that gate specific tasks; those are flagged inline and listed up front.

**Goal:** Wire the fixed 13-stage DAG into the existing orchestrator so a golden study runs end-to-end under stubbed LLM nodes — Stage-1A stages as thin adapters over their certified modules, Stage-1B stages (narrate/gate2/package) as certification pass-through stubs — satisfying AT-M15-1..6 (IT-1..IT-3) and re-enabling M5 C4.

**Architecture:** The orchestrator (`core/orchestrator.py`), `Stage` protocol, `StageContext`, manifest/provenance/results-store, compliance and advisory generators, and every Stage-1A statistical module already exist and are individually certified. TC-15 adds (1) thin `Stage`-shaped adapters that call the existing module functions, (2) three deterministic pass-through stubs for S9/G2/S10, (3) a non-empty `_production_registry()`, (4) the CLI `run`/`rerun` wiring that builds a run dir + manifest fields and invokes `Orchestrator.run`, (5) deterministic stubbed Node A / Node C providers, (6) a `burhan doctor` `BURHAN_CERTIFIED_WORKSTATION` marker line (P3), and (7) the `tests/integration/` IT-1..IT-3 harness.

**Tech stack:** Python 3.12, typer CLI, pydantic v2 artifacts, the R worker bridge (`RWorker`), pytest. No new dependencies.

---

## 0. Open decisions — REQUIRE A RULING (they gate the flagged tasks)

Interface research turned up four contract-vs-reality tensions. Per CLAUDE.md rule 2 I surface them rather than silently resolve; each carries my recommendation. Tasks that depend on a ruling are marked **[GATED: D#]**.

### D1 — Compliance checklist must cover all **21** playbook steps, not 19
`playbooks/CB_SEM_PLAYBOOK_v1.0.yaml` declares **PB-01..PB-21** (verified). PB-01..PB-19 are the Stage-1A steps; **PB-20 = narrate, PB-21 = package** (Stage-1B). `core/compliance.py::Compliance.render()` enumerates **every** `playbook.step_ids` and **halts** unless each is `mark`ed. AT-M15-1 says the checklist "covers PB-01..PB-19 (the Stage-1A playbook steps)" — literally true for what's genuinely completed, but the file cannot render unless PB-20/PB-21 are also marked. The three statuses are `completed | failed | flagged`; `completed` additionally requires every `playbook.outputs(step_id)` prefix to be present in the ResultsStore. There is **no "stubbed/deferred" status.**
- **Recommendation:** the S9/S10 pass-through stubs `mark(PB-20/PB-21, "flagged", "certification pass-through; real narrate/package behavior deferred to TC-13/TC-14")`. `render()` then succeeds; the checklist honestly shows 19 Stage-1A steps `completed` and 2 Stage-1B steps `flagged`-as-deferred. AT-M15-1's "PB-01..PB-19" = the genuinely-completed set.
- **Ruling needed:** accept `flagged` for pass-through **or** direct me to add a `stubbed` status to `COMPLIANCE_STATUSES` (a `core/compliance.py` change — beyond "adapters over existing code"; needs explicit authorization). I do **not** want the stubs to fabricate `completed` by writing fake narrate/package outputs.

### D2 — The playbook is `draft`; `burhan run` in production mode halts (P5)
`meta.status: draft` (verified). `Playbook.load(mode="production")` halts unless `approved`; `Policy`/`Registry` likewise. Every existing suite loads `mode="certification"`. AT-M15-4 requires `burhan run` on a golden study to reach `COMPLETED` — impossible in production mode against a draft playbook.
- **Recommendation:** for TC-15/M5, `burhan run` loads governance in **certification mode** (the golden *certification* run), matching all existing suites; production mode awaits the researcher's playbook **approval** (a Wave-4 milestone, out of TC-15 scope).
- **Ruling needed:** how should `burhan run` select the mode? (a) a `--certify` flag (explicit, recommended); (b) auto-select by `meta.status` (certification while draft, production once approved); (c) hard-code certification for now with a TODO tied to approval. I recommend (a) or (b) to avoid a hidden hard-code. If instead `burhan run` must be production-only, **AT-M15-4 is blocked** until the playbook is approved (a governed change outside TC-15) — that would itself be a finding to escalate.

### D3 — The golden generator cannot produce an adequately-powered study for IT-1
`build_golden` emits ~41 cases (`_N_CLEAN = 32` hard-coded + 9 planted); the golden model has `q = 26` free params → **N:q ≈ 1.6:1**, far below the PB-01 **5:1 absolute floor**. So `power_gate` fires `AdvisoryStop` for *any* golden bundle. That makes **IT-3 (COMPLETED_TO_BOUNDARY) trivial** (feed the golden study or `n=100`), but **IT-1 (COMPLETED) needs the power gate to pass** — i.e. N ≥ 130 for this model.
- **Recommendation:** build an integration-only **adequately-powered golden fixture** (≥130 clean cases for the golden model) under `tests/integration/fixtures/`, reusing `generator.py`'s row machinery with a raised clean-N (either a new `n_clean` parameter on `build_golden` — a **test-code** change — or a purpose-built integration builder). This is fixture/test code, authorized by §6.
- **Ruling needed (light):** confirm "extend the generator with an `n_clean` parameter" vs "separate integration fixture builder." I can decide this as fixture design, but flag it because it is load-bearing for IT-1 and touches `tests/golden/generator.py`.

### D4 — `measurement` and `structural` have no store-row builders (complexity note, likely not a blocker)
`effects.py` and `robustness.py` ship `*_store_rows` (directly writable); `power.py`/`assumptions.py` ship builders that **embed** the store-owned `schema_version`/`created`/`hash` (the adapter must strip them — `ResultsStore.write` halts otherwise). But `measurement.py` and `structural.py` return rich dicts with **no** row builder. To `mark(PB-08..PB-16, "completed", …)` compliance requires those stages' `playbook.outputs` prefixes present in the store, so the measurement/structural adapters must **serialize their returned dicts into store rows** matching those prefixes.
- **Recommendation:** the measurement/structural adapters build store rows from the existing return dicts (serialization/wiring, *not* new statistical behavior — consistent with "adapters call existing code"). This makes those two adapters thicker than one-liners. If serialization proves impossible without changing module behavior, I STOP and escalate per TC-15's own clause.
- **Ruling needed (light):** acknowledge that measurement/structural adapters include result→store-row serialization within "adapter" scope (no statistical change), or direct that `*_store_rows` builders be added to those modules instead (a `stats/` change — needs authorization).

---

## 1. Grounded interface facts (the plan builds on these; file:line verified)

**Stage protocol** (`core/orchestrator.py:85-94`): attrs `name: str`, `consumes: tuple[str,...]`, `produces: tuple[str,...]`, method `execute(self, ctx: StageContext) -> None`; raise a taxonomy halt on failure. `_check_registry` only enforces key coverage of `PIPELINE`, not the attrs. Reference impl: `StubStage` (`tests/unit/orchestrator/orch_util.py:29-43`).

**StageContext** (`orchestrator.py:71-83`, frozen): `run_dir`, `stage`, `stage_seed`, `master_seed`, `clock`, `manifest`, `provenance`, `store`. It carries **no** frame/config/policy/playbook/rworker/call_id — each adapter materializes those (frame from a prior stage's run-dir artifact; config from the contract artifact; governance via `load_governance(...)`; a constructed `RWorker`; a derived `call_id`). Stages needing governance/LLM stubs **close over** them (constructed before registry placement).

**PIPELINE** (`orchestrator.py:41-55`): `ingest, contract, gate1, power, prep, assumptions, measurement, structural, effects, robustness, narrate, gate2, package`. `Orchestrator(clock).run(run_dir, registry, manifest_fields=…) -> RunResult(state, run_dir, report_path)`. `rerun(source, registry, target_run_dir=…)` re-runs and asserts byte-identity (excl. `manifest.json`).

**Terminal states**: any `BurhanHalt` in a stage → `_terminate`; `AdvisoryStop` (`errors.py:69-72`, `run_state="COMPLETED_TO_BOUNDARY"`) marks tail stages `SKIPPED_BOUNDARY`, no NON_FINAL marker; other halts write NON_FINAL. Success → `COMPLETED`. Exit map `cli/__init__.py:24-30`.

**ResultsStore.write** (`results/store.py:55`): owns `schema_version`/`created`/`hash` (halts if supplied); enforces `id.split(".",1)[0] == fields["stage"]`; rejects duplicate ids.

**Manifest.open** (`manifest.py:93`) consumes `manifest_fields` (must omit the 6 manifest-owned keys `schema_version/started/state/stages/finished/seal`); `master_seed` read by key; `RunManifest` shape at `models.py:372-388` requires `run_id` (`^[0-9]{8}T[0-9]{6}Z$`), `study_id`, `master_seed`, `engine`, `hashes`, `environment` (`doctor_passed: Literal[True]`), `llm_nodes`. Test helper `manifest_fields()` (`orch_util.py:54-99`) is the copyable shape.

**Stage-1A entry points** (all verified; `run_dir`/`store` from `ctx`, `created` from `ctx.clock`):
| Stage | Call | RWorker | Store rows |
|---|---|---|---|
| power | `power_gate(config, *, n, playbook, advisory)` (+`power_store_rows(config,*,n,playbook,created)`) | no (gate); MC in `montecarlo.py` | rows **embed owned fields → strip** |
| prep | `run_prep(export_path, config, policy, *, mcar_alpha=.05, treatment_select="primary") -> PrepResult(.frame,…)` | no | PrepResult (frame + payloads) |
| assumptions | `univariate_moments/mardia/vif_composites/mahalanobis_feed`, `estimator_determination(...)`, `assumptions_store_rows(frame,*,playbook,created)` | no | rows **embed owned fields → strip** |
| measurement | `run_measurement(frame,config,*,policy,playbook,rworker,run_dir,call_id,approach=None)` (+`run_cmb(...)`) | **yes** | **no builder — D4** |
| structural | `run_structural(frame,config,*,playbook,rworker,run_dir,call_id)` | **yes** | **no builder — D4** |
| effects | `run_effects(frame,config,*,policy,playbook,rworker,run_dir,call_id)`, `effects_store_rows(report)` | **yes** | directly writable |
| robustness | `run_alternatives(frame,config,*,playbook,rworker,run_dir,call_id)`, `achieved_power_report(config,*,n,playbook)`, `robustness_store_rows(report,power)` | **yes** | directly writable |

**Ingest chain**: Node A (`contract/node_a.py::NodeA.extract(*, study_document, …) -> StudyConfig`) → `contract/crosswalk.py::build_crosswalk(export_path, config)` → `prep/py_impl/pipeline.py::run_prep(...)`. R-backed stages hard-code `seed=1` in `rworker.call` (deterministic — good for IT-2).

**LLM stubs**: adapters take `provider_call: Callable[[str], str]` (`contract/llm_base.py:212`). Node A stub returns schema-valid `study_config` YAML; Node C stub returns `{"verdict":"approve","fixes":[]}` (`review/node_c.py::parse_verdict`, closed 2-key schema). Build `LlmSettings` directly for fixtures (pattern: `tests/unit/contract/contract_util.py`, `tests/unit/review/review_util.py`).

**Compliance** (`core/compliance.py`): `Compliance(playbook, store, path, clock)`; `mark(step_id, status, evidence)`; `render() -> str` (caller writes the file). **Advisory** (`core/advisory.py`): `Advisory(directory, provenance, clock).emit(*, stage, trigger, diagnostics, recommendation, citations, impact) -> NoReturn` writes `METHOD_ADVISORY.md` then raises `AdvisoryStop`. **Doctor** (`cli/doctor.py`): `DoctorCheck(name, status, detail)` appended in `run_doctor` before the return; `passed = all(status != "fail")`.

**Study dir layout** (`03_ARCHITECTURE.md:76,154-169`): `studies/<study>/{inputs,config,runs,outputs}`; run archive under `runs/<UTC>/`. No sample study dir is committed — the IT harness builds one from the golden bundle (`GoldenStudy.write(dir)` → CSV; config dict → `config/study_config.yaml`).

---

## 2. File structure

**Create (src):**
- `src/burhan/stages/__init__.py` — the stages subpackage.
- `src/burhan/stages/context.py` — shared adapter helpers: materialize governance (`load_governance` in the D2-chosen mode), load the frame from the prep artifact, derive `call_id`, strip store-owned fields, read analytical N.
- `src/burhan/stages/stage_1a.py` — the 10 Stage-1A adapters (ingest, contract, gate1, power, prep, assumptions, measurement, structural, effects, robustness).
- `src/burhan/stages/stub_1b.py` — the 3 Stage-1B pass-through stubs (narrate, gate2, package), clearly namespaced `Stub*`.
- `src/burhan/stages/registry.py` — `production_registry(*, clock, provider_calls, mode) -> dict[str, Stage]` assembling all 13.

**Modify (src):**
- `src/burhan/cli/__init__.py` — `_production_registry()` returns the assembled 13; `run(study_dir)` builds run dir + `manifest_fields` + invokes `Orchestrator.run`; `rerun(run_dir)` invokes `Orchestrator.rerun`; import `Orchestrator`.
- `src/burhan/cli/doctor.py` — add the `certified_workstation` `DoctorCheck` (P3, **D-independent**).

**Create (tests/fixtures):**
- `tests/fixtures/stub_nodes.py` — deterministic Node A / Node C provider callables (canned schema-valid config YAML; approve verdict).
- `tests/integration/fixtures/` — the adequately-powered golden study bundle for IT-1 **[GATED: D3]**.

**Create (tests/integration):**
- `tests/integration/conftest.py` — sys.path bootstrap (mirror `tests/golden/conftest.py`).
- `tests/integration/test_it1_dry_run.py` — AT-M15-1.
- `tests/integration/test_it2_rerun_identity.py` — AT-M15-2.
- `tests/integration/test_it3_boundary.py` — AT-M15-3.
- `tests/integration/test_it4_registry.py` — AT-M15-4.
- `tests/integration/test_it6_stub_boundary.py` — AT-M15-6.

**Modify (docs):** `docs/00_DOC_INDEX.md` already updated at `a22b929`; no further doc edits beyond this plan and the eventual completion report.

---

## 3. Task breakdown (TDD; each task = failing test → minimal impl → green → commit)

Order respects dependencies: the P3 doctor line and the stub/adapter units come before the full-pipeline IT tests. Every task writes the test first, watches it fail, then implements.

### Task 1 — P3 doctor marker line (AT: P3 closure; **not gated**)
- **Test** (`tests/unit/orchestrator/test_cli.py` or a doctor test): `run_doctor(inputs).render()` contains a line `certified_workstation` whose detail names `BURHAN_CERTIFIED_WORKSTATION` and whose status reflects the env var (`pass` when `=1`, else `skip`); `report.passed` unaffected when unset.
- **Impl**: in `cli/doctor.py::run_doctor`, before the `return`, `checks.append(DoctorCheck("certified_workstation", "pass" if os.environ.get("BURHAN_CERTIFIED_WORKSTATION")=="1" else "skip", "BURHAN_CERTIFIED_WORKSTATION=<...>; certified-workstation marker"))`. Never `fail` (a marker-absent host must still pass doctor). Commit.

### Task 2 — stubbed Node A / Node C providers (fixtures; supports AT-M15-1..4)
- **Test** (`tests/unit/contract`/`review` style): the stub Node A `provider_call` fed to `NodeA(...).extract(study_document=…)` returns the golden `StudyConfig`; the stub Node C `provider_call` yields an `approve` `Verdict` via `parse_verdict`.
- **Impl**: `tests/fixtures/stub_nodes.py` — `node_a_provider(config_dict) -> Callable[[str],str]` returns `lambda _prompt: yaml.safe_dump(config_dict)`; `node_c_approve_provider() -> Callable[[str],str]` returns `lambda _prompt: yaml.safe_dump({"verdict":"approve","fixes":[]})`. Commit.

### Task 3 — Stage-1B pass-through stubs + boundary (AT-M15-6; **[GATED: D1]** for the compliance-marking detail)
- **Test** (`test_it6_stub_boundary.py`): each `StubNarrate/StubGate2/StubPackage` satisfies the `Stage` protocol, `execute(ctx)` writes only a schema-valid placeholder artifact + (narrate/package) `mark`s its PB step per **D1**, and a source-inspection probe asserts the stub module imports **no** narrate/checker/reporting/APA/SPSS symbols (AT-M15-6). Replacing a stub with its real stage later needs no unwiring (registry keys stable).
- **Impl**: `src/burhan/stages/stub_1b.py`. Each stub: `name`, `consumes=()`, `produces=(…placeholder…)`, `execute` writes a minimal marker file under `ctx.run_dir` and appends provenance `event_type="stage_complete"`, `notes="certification pass-through stub (TC-15); real behavior TC-13/TC-14"`. Narrate/package additionally `Compliance(...).mark(PB-20/PB-21, "flagged", …)` per D1. Commit.

### Task 4 — Stage-1A adapters (AT-M15-5 guards no drift; **[GATED: D2]** governance mode, **[GATED: D4]** measurement/structural serialization)
Worked pattern (structural, representative of the R-backed adapters):
```python
class StructuralStage:
    name = "structural"
    consumes = ("prep.frame", "contract.study_config")
    produces = ("stats/structural.json",)
    def __init__(self, *, governance, rworker_factory):
        self._gov, self._rworker_factory = governance, rworker_factory
    def execute(self, ctx: StageContext) -> None:
        config = load_study_config(ctx.run_dir)          # from contract artifact
        frame = load_prep_frame(ctx.run_dir)             # from prep artifact
        report = run_structural(frame, config, playbook=self._gov.playbook,
                                rworker=self._rworker_factory(), run_dir=ctx.run_dir,
                                call_id=f"{ctx.stage}-{ctx.stage_seed}")
        for row in structural_store_rows(report, created=fmt(ctx.clock.now())):  # D4 serialization
            ctx.store.write(row)
```
- **Tests**: one per adapter — construct `StageContext` against a `tmp_path` seeded with the upstream artifacts, run `execute`, assert the expected `store` ids / artifacts appear; power adapter's below-floor path raises `AdvisoryStop` (drives IT-3). Reuse `structural_util`/`generator` fixtures.
- **Impl**: `src/burhan/stages/stage_1a.py`; `context.py` helpers incl. `_strip_owned(row)` for power/assumptions rows and the D4 serializers. **No statistical behavior added** — adapters only call the certified functions and serialize their returns. Commit per adapter.

### Task 5 — `production_registry()` + CLI wiring (AT-M15-4; **[GATED: D2]**)
- **Test** (`test_it4_registry.py`): `production_registry(...)` returns exactly the 13 `PIPELINE` keys in DAG order; an independent probe runs `burhan run <golden-study-dir>` and asserts exit ≠ 10 and terminal `COMPLETED` (using the D3 adequately-powered fixture + stub providers).
- **Impl**: `src/burhan/stages/registry.py::production_registry`; `cli/__init__.py::_production_registry()` calls it (closing over real `provider_call`s in production; the IT harness injects stubs). `run(study_dir)` derives `run_dir = study_dir/"runs"/<UTC>`, assembles `manifest_fields` (RunManifest shape, `environment.doctor_passed=True` from a doctor call, hashes from governance files), `Orchestrator(SystemClock()).run(...)`, `raise typer.Exit(EXIT_BY_STATE[result.state])`. Commit.

### Task 6 — IT-1 dry run (AT-M15-1; **[GATED: D1, D3]**)
- **Test** (`test_it1_dry_run.py`): build the adequately-powered golden study dir (D3), inject stub providers, run the full pipeline → `RunResult.state == "COMPLETED"`; assemble `METHOD_COMPLIANCE_CHECKLIST.md` via `Compliance.render()` and assert it contains PB-01..PB-21 rows with PB-01..PB-19 `completed` and PB-20/PB-21 `flagged` (D1); every stage recorded in the sealed manifest.
- **Impl**: harness helpers to lay down the study dir + drive `Orchestrator.run`; the compliance file is written by the package stub (or a harness step) from the marks accumulated across stages. Commit.

### Task 7 — IT-2 rerun identity (AT-M15-2)
- **Test** (`test_it2_rerun_identity.py`): `Orchestrator.rerun(sealed_it1_run, registry, target_run_dir=…)` → byte-identical artifacts; then plant nondeterminism in a stub (e.g. a stub writing `ctx.clock.now()` unrounded) and assert `VerificationHalt` names the differing file.
- **Impl**: none beyond Task 5 if stages are already deterministic (R calls use fixed `seed=1`; clocks injected). Add the negative-control stub in test scope only. Commit.

### Task 8 — IT-3 boundary (AT-M15-3)
- **Test** (`test_it3_boundary.py`): drive the pipeline with an under-powered fixture (the stock `build_golden` bundle or `n=100`) → `power` stage `emit`s the advisory → `RunResult.state == "COMPLETED_TO_BOUNDARY"`, `METHOD_ADVISORY.md` present, tail stages `SKIPPED_BOUNDARY`, exit 0.
- **Impl**: none beyond the power adapter's advisory path (Task 4). Commit.

### Task 9 — AT-M15-5 whole-suite green + gates
- Run the entire pre-existing unit + golden + benchmark suite unchanged → all green (proves no statistical/Stage-1B behavior leaked). Run ruff/format/mypy/pytest+coverage/lintr. Commit.

---

## 4. How each acceptance test is satisfied

| AT | Satisfied by | Gated on |
|---|---|---|
| AT-M15-1 (IT-1 COMPLETED + checklist) | Task 6 (+2,3,4,5) | D1, D3 |
| AT-M15-2 (rerun byte-identity) | Task 7 | — |
| AT-M15-3 (boundary → COMPLETED_TO_BOUNDARY) | Task 8 (+4 power advisory) | — |
| AT-M15-4 (registry exact 13 + run ≠ exit 10 → COMPLETED) | Task 5 | D2, D3 |
| AT-M15-5 (no Stage-1A drift; whole suite green) | Task 9 | — |
| AT-M15-6 (stub boundary; no 1B logic) | Task 3 | D1 |

## 5. Self-review (spec coverage vs TC-15)
- In-scope deliverables (TC-15.md:29-37): 13-stage registry ✓(T5), Stage-1A thin adapters ✓(T4), Stage-1B stubs ✓(T3), stubbed Node A/C ✓(T2), non-empty registry ✓(T5), `tests/integration/` IT harness ✓(T6-8), doctor marker line ✓(T1), DOC_INDEX ✓(done at a22b929). All present.
- Out-of-scope respected: no Stage-1A statistical change (T4/T9 guard), no real Stage-1B behavior (T3 boundary + AT-M15-6), no governed-doc edits beyond DOC_INDEX + this plan, no new deps. The only judgement calls that could touch `src/` beyond adapters (D1 status enum, D4 module row-builders) are explicitly escalated, not assumed.
- Risks: D1/D2 touch governed/tool semantics; D3/D4 are fixture/serialization scope. Tasks are ordered so the doctor line (T1) and unit-level stubs/adapters (T2-4) land before the full-pipeline IT tests (T6-8), keeping each commit green.

---

**Requested of the reviewer:** rulings on D1 and D2 (and light confirmation on D3, D4) before I begin Task 1, so implementation doesn't proceed on an assumption about governed semantics. On approval I implement test-first in the task order above; then the full M5 battery re-executes from §1.
