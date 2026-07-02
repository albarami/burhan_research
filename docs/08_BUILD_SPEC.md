# Burhān — Phase 1 Build Specification (docs/08_BUILD_SPEC.md)

**Scope:** Phase 1 — CB-SEM v1 Core Release (Stages 1A → 1B)
**Status:** For review
**Governed by:** `01_CONCEPT.md`, `02_REQUIREMENTS.md` (FR/NFR), `03_ARCHITECTURE.md` (AD-01..08, component map §3), `04_ENVIRONMENT_AND_STACK.md`, `05_schemas/`, `06_playbooks/`, `07_policy/`, `15_ENGINEERING_STANDARDS.md`.
**Consumed by:** Codex (direction), `09_task_contracts/` (work orders), `10_PROJECT_PLAN.md` (milestones).

**Reading rule.** Modules are the unit of design; task contracts are the unit of work. Most modules map to one contract; M08 splits into three and M10/M11 into two each (noted inline). Acceptance tests are named `AT-Mxx-n`; every test cites the requirement it proves and must fail when the behavior is removed (standards §3).

---

## 0. Module Index & Dependency Order

| # | Module | Stage | Depends on | Contracts |
|---|---|---|---|---|
| M01 | core-foundation | 1A | — | TC-01 |
| M02 | governance | 1A | M01 | TC-02 |
| M03 | playbook-engine | 1A | M01, M02 | TC-03 |
| M04 | orchestrator-cli + R harness | 1A | M01–M03 | TC-04 |
| M05 | ingest-crosswalk | 1A | M01, M04 | TC-05 |
| M06 | node-a-contract | 1A | M01, M04, M05 | TC-06 |
| M07 | node-c-gates | 1A | M06 | TC-07 |
| M08 | prep-dual | 1A | M04, M05 (contract fixture from M06) | TC-08a/b/c |
| M09 | power-assumptions | 1A | M04, M08 | TC-09 |
| M10 | measurement | 1A | M09 | TC-10a/b |
| M11 | structural-effects | 1A | M10 | TC-11a/b |
| M12 | robustness-verify | 1A | M11 | TC-12 |
| M13 | narrate | 1B | M07, M11, M12 | TC-13 |
| M14 | package | 1B | M13 | TC-14 |

Build order is the table order; a module starts only when its dependencies carry APPROVE in SIGNOFFS (AGENTS.md). Certification infrastructure is distributed by design: the **golden-dataset generator + suite** ships inside M08 (its own acceptance depends on it, FR-1501); the **benchmark replication runner** ships inside M12 (FR-1502); the **reference-comparison builder** ships inside M12 (FR-1503).

---

## M01 — core-foundation

**Purpose.** Everything every other module stands on: schema-bound artifact models, canonical serialization, hashing and seed derivation, the run manifest, the provenance (sanad) appender, the append-only results store with ID resolution, the typed failure taxonomy, structured logging.

**Maps to (03 §3):** `core/artifacts`, `core/manifest`, `core/provenance`, `results/store`.

**Interface (indicative).**
`artifacts.load_yaml(path, schema) -> Model` · `canonical.dumps(obj) -> str` · `seeds.derive(master, stage, worker) -> int` · `Manifest.open/record_stage/seal` · `Provenance.append(entry)` · `ResultsStore.write(entry)/resolve(id)/iter(prefix)` · exceptions `IntegrityHalt/VerificationHalt/GateExhausted/AdvisoryStop`.

**Consumes/produces.** Consumes `docs/05_schemas/*`; produces `manifest.json`, `PROVENANCE.jsonl`, `results/results.jsonl + index.json` inside a run dir.

**Traces.** FR-1001, FR-1109 (partial), FR-1403 (layout), NFR-101/102/201/301.

**Acceptance tests.**
- AT-M01-1: every schema in `05_schemas` loads; a valid instance round-trips model→canonical JSON→model byte-identically; an invalid instance raises with the schema path (FR-203 pattern, NFR-201).
- AT-M01-2: canonical serializer is order- and float-stable — permuted dict input yields identical bytes; repeated runs yield identical hashes (NFR-101).
- AT-M01-3: seed derivation is deterministic and collision-tested across (stage, worker) pairs; changing the master seed changes all derived seeds (NFR-101).
- AT-M01-4: results store rejects duplicate IDs, rejects IDs violating the grammar, resolves prefixes correctly; store file is append-only (mutation attempt fails) (FR-1001, AD-05).
- AT-M01-5: provenance `seq` is strictly increasing and gap-free under concurrent stage writes; entries validate against the schema (NFR-301).
- AT-M01-6: manifest seal computes a hash-tree root; any post-seal file change is detected by `verify_seal()` (NFR-102).

---

## M02 — governance

**Purpose.** The policy engine and the protected boundary: load/validate `decision_policy` (D1–D3) and the registry (R1–R3), evaluate rules with decision-log emission, expose the *recommendation-only* API for protected decisions, and emit `METHOD_ADVISORY.md`.

**Maps to:** `core/policy`, `core/registry`.

**Interface.** `Policy.load(path) -> Policy` (validates, exposes `rule(path)`), `Policy.decide(decision_point, inputs) -> Decision` (writes DecisionEntry) · `Registry.load(path)` · `Registry.guard(decision_id)` → returns a `Recommendation`/`Advisory` object; **there is no execute method** · `Advisory.emit(diagnostics, recommendation, citations, impact)`.

**Traces.** FR-1201–1204, FR-403 (advisory path), D1–D3, R1–R3.

**Acceptance tests.**
- AT-M02-1: template policy and registry validate; `status: draft` blocks a production-mode load; every leaf path is addressable via `rule()` (D1, FR-1201).
- AT-M02-2: all 10 playbook `policy_ref`s and the registry `delegation_ref` resolve at load (D2/R2); an unresolvable ref fails load with the missing path named.
- AT-M02-3 (absence test): the registry API exposes no execution path for PD-01..PD-05 — introspection proves no such method exists; requesting execution raises by construction (FR-1202).
- AT-M02-4: with `item_deletion.preauthorized: false`, a deletion candidate yields a `Recommendation` and a DecisionEntry with `protected` unset; flipping to `true` yields an executable *permit token* consumed only by M10's protocol (FR-705, PD-05).
- AT-M02-5: `Advisory.emit` produces a schema-conformant `METHOD_ADVISORY.md` + provenance entry and sets the run toward `COMPLETED_TO_BOUNDARY` (FR-1203).
- AT-M02-6: every `decide()` writes a DecisionEntry citing rule id + policy version; the rendered DECISION_LOG.md contains nothing absent from the JSONL (schema promise).

---

## M03 — playbook-engine

**Purpose.** Load and cross-check playbooks (P1–P5), expose steps/criteria/citations to stages, and track compliance rows for the checklist.

**Maps to:** `core/playbook`.

**Interface.** `Playbook.load(path)` (schema + P1–P5) · `Playbook.step(id)` / `criteria(id)` · `Compliance.mark(step_id, status, evidence)` · `Compliance.render() -> METHOD_COMPLIANCE_CHECKLIST.md`.

**Traces.** FR-1301–1303, FR-1106; P1–P5.

**Acceptance tests.**
- AT-M03-1: `CB_SEM_PLAYBOOK_v1.0.yaml` loads; a mutated copy violating each of P1–P4 fails load with the specific check named.
- AT-M03-2: `status: draft` playbook blocks production-mode load (P5); certification mode may load draft.
- AT-M03-3: an undeclared/unknown methodology in a contract produces the clean refusal with report — no partial run artifacts (FR-1302).
- AT-M03-4: compliance render lists every playbook step exactly once with status completed/failed/flagged; a step whose `outputs` prefixes are absent from the results store cannot be marked completed (FR-1106).

---

## M04 — orchestrator-cli + R harness

**Purpose.** The typed state machine over the fixed DAG; CLI (`run`, `rerun`, `certify`, `doctor`); halt-class mapping; run-dir lifecycle and seal; the file-based Rscript worker harness (call contract, renv assertion, seed injection, error propagation); rerun byte-identity.

**Maps to:** `cli/`, `core/orchestrator`, interop of 03 §6.

**Interface.** `burhan run <study-dir>` / `rerun <run-dir>` / `certify` / `doctor` · `Stage` protocol (`consumes`, `produces`, `execute(ctx)`) · `RWorker.call(module, payload) -> payload`.

**Traces.** FR-306, FR-1204, FR-1401/1403; AD-01/02/03; NFR-201/202/501/502; NFR-101 (rerun); doctor per 04 §9.

**Acceptance tests.**
- AT-M04-1: state transitions follow 03 §4 exactly; an unregistered transition is impossible (typed); every terminal state writes its report (NFR-201).
- AT-M04-2: after Gate-1-pass, no code path reads stdin/interactive input — proven by running the full stub pipeline with stdin closed (FR-306, FR-1401).
- AT-M04-3: injected faults map to the correct halt class — invariant fail→`HALTED_INTEGRITY`, parity breach→`HALTED_VERIFICATION`, gate exhaustion→`HALTED_GATE`, advisory→`COMPLETED_TO_BOUNDARY`; partial artifacts preserved and marked (FR-1204, NFR-202).
- AT-M04-4: `rerun` on a sealed stub run regenerates byte-identical artifacts; a planted nondeterminism (unseeded RNG in a stub stage) is caught by the identity assertion (NFR-101, FR-1403).
- AT-M04-5: R harness — worker gets derived seed + payload file; nonzero exit, schema-invalid output, or renv drift each produce `HALTED_INTEGRITY` with captured stderr (AD-02, NFR-102).
- AT-M04-6: `doctor` fails on each simulated violation (wrong BLAS threads, missing key, lineage(A)==lineage(C), dirty renv) and passes on the reference setup; manifest records `doctor_passed: true` only then (04 §9).

---

## M05 — ingest-crosswalk

**Purpose.** File integrity; Qualtrics-dialect parsing (multi-header exports); column→item crosswalk from embedded item codes; zero-orphan column accounting; structural match against the contract's data block.

**Maps to:** `contract/crosswalk`.

**Traces.** FR-101–104, FR-103; V6 accounting (05 schema rules); FR-507 (orphans).

**Acceptance tests.**
- AT-M05-1: a 3-header Qualtrics fixture yields a complete crosswalk with item codes parsed from row-2 text; ambiguous or duplicate item codes raise `IntegrityHalt` naming the columns (FR-103/104).
- AT-M05-2: zero-orphan accounting — a fixture with one undeclared column fails with that column named; declaring it in `metadata_columns`/`ignored_item_columns` passes (FR-507, V6).
- AT-M05-3: declared-but-absent item columns (contract says R9 exists; export lacks it) raise structural mismatch (FR-104).
- AT-M05-4: xlsx and csv fixtures produce identical crosswalks and identical raw-frame hashes (FR-101).

---

## M06 — node-a-contract

**Purpose.** The LLM adapter base (provider config, lineage validation, allowlists, deterministic settings, prompt version hashing) plus Node A: study document → `study_config.yaml`, schema validation, cross-field validators V1–V7, data-dictionary cross-check.

**Maps to:** `contract/node_a`, `contract/validators`, shared adapter base.

**Traces.** FR-201–206; FR-304 (lineage check lives in the base); AD-04; NFR-401/402.

**Acceptance tests.**
- AT-M06-1 (allowlist/absence): passing a raw-data path or frame to any adapter raises at the boundary; test enumerates adapter inputs to prove the allowlist is closed (FR-206, NFR-401).
- AT-M06-2: config with `lineage(A)==lineage(C)` fails startup validation (FR-304).
- AT-M06-3: on a fixture study document (the schemas' worked example rendered to prose), Node A output validates and V1–V7 all pass; seven mutated documents each trip exactly their validator with a hard failure — no guessing (FR-203/205).
- AT-M06-4: dictionary conflict (dictionary says RS3 reverse-coded, document silent) → hard failure citing the conflict (FR-204).
- AT-M06-5 (absence): no field of the produced contract can encode a retained subset — schema property test over the model (FR-202).
- AT-M06-6: prompt template version + hash land in the manifest; changing the template changes the hash (AD-04, NFR-102).

---

## M07 — node-c-gates

**Purpose.** The Muḥāsaba reviewer: Gate 1 (contract vs source) and Gate 2 (draft vs results store + decision log), schema-bound verdicts, bounded retry loop.

**Maps to:** `review/node_c`.

**Traces.** FR-301–305, FR-303 retries via `gates.max_retries`.

**Acceptance tests.**
- AT-M07-1: Gate 1 approves the faithful fixture contract; each seeded corruption (dropped hypothesis, swapped mapping, wrong methodology, missing reverse-code) yields REJECT with fixes naming the defect (FR-301).
- AT-M07-2: Gate 2 rejects a draft containing an unsupported claim / omitted failed hypothesis against a fixture results store (FR-302).
- AT-M07-3: retry loop — author-node stub fixes on fix-list; loop terminates ≤ `max_retries`; exhaustion → `HALTED_GATE` with final verdict archived (FR-303).
- AT-M07-4 (absence): Node C has no write access to artifacts and no compute API — introspection + attempted-call tests (FR-305).
- AT-M07-5: schema-invalid verdict from the model counts as a reject-cycle, not a crash (FR-303).

---

## M08 — prep-dual  *(contracts TC-08a Python impl · TC-08b R impl + reconciler · TC-08c golden suite)*

**Purpose.** The full preparation sequence twice (Python, R), cell-level reconciliation, hard invariants, exact N-chain accounting, and the golden-dataset generator + certification suite.

**Maps to:** `prep/*`, `tests/golden/`.

**Traces.** FR-501–507; FR-1501; NFR-601 (golden as regression).

**Acceptance tests.**
- AT-M08-1: on the golden dataset, the Python pipeline detects 100% of planted defects by class (duplicates, attention fails, straight-liners, out-of-range, un-reversed, engineered missingness, known outliers) with zero false positives on clean twins (FR-1501).
- AT-M08-2: partial-response recovery — cases ≥ policy threshold on model items enter the sample; profile artifact lists every partial with its completion %; threshold is read from policy, not code (FR-502).
- AT-M08-3: N-chain sums exactly at every link on golden and on an adversarial fixture (overlapping defect classes); a planted double-count breaks the run with `IntegrityHalt` (FR-506).
- AT-M08-4 (absence): no mean-substitution and no synthetic-case code path exists — absence tests per standards §3 (FR-505).
- AT-M08-5: invariants — each of the seven FR-507 assertions has a fixture that trips exactly it.
- AT-M08-6: R impl on golden matches Python **cell-for-cell at tolerance 0**; a planted one-cell divergence halts with a discrepancy report naming row/column (FR-501).
- AT-M08-7: Little's MCAR + pattern map computed before treatment; FIML selected under MCAR fixture, MI under the policy-alternative fixture, MNAR fixture flags with sensitivity note (FR-503/504).
- AT-M08-8: reverse-coding verified by sign-flip; an un-reversed golden item is caught here even if declared correctly (FR-507).

---

## M09 — power-assumptions  *(R stats begin)*

**Purpose.** A priori power (MacCallum close-fit, N:q, simsem Monte Carlo), distributional and collinearity diagnostics, Mahalanobis feed, and the estimator determination per PB-07 with logged rationale.

**Maps to:** `stats/power`, `stats/assumptions`.

**Traces.** FR-401–403; FR-601–603; PB-01/05/06/07.

**Acceptance tests.**
- AT-M09-1: close-fit power reproduces the MacCallum et al. (1996) published table values at (df, N) test points within 0.001 (FR-401, FR-1502-adjacent).
- AT-M09-2: N:q computed from the contract's free-parameter count; below-floor fixture triggers the advisory path via M02 (FR-403).
- AT-M09-3: Mardia + univariate bands on a known-answer fixture match `MVN`/`psych` reference outputs; results land under `assumptions.*` IDs (FR-601).
- AT-M09-4: estimator determination — three fixtures (clean → ML; Mardia-violating → MLR; 4-category → WLSMV) each produce the right determination **and** a DecisionEntry with rationale + citations (FR-602/603).
- AT-M09-5: Monte Carlo power is seed-deterministic — identical seeds ⇒ identical power estimates (NFR-101).

---

## M10 — measurement  *(TC-10a CFA/validity/CMB · TC-10b deletion + respecification)*

**Purpose.** CFA incl. second-order (both approaches), reliability/convergent/discriminant (α, CR, AVE, Fornell–Larcker, HTMT), CMB (Harman + CLF/marker), the item-deletion protocol behind M02's permit token, and the respecification controller.

**Maps to:** `stats/measurement`.

**Traces.** FR-701–709; PB-08–PB-14.

**Acceptance tests.**
- AT-M10-1: on a published higher-order worked example, first- and second-order loadings, α/CR/AVE match reference within tolerance; both-level reporting present (FR-701/702, FR-1502).
- AT-M10-2: HTMT and Fornell–Larcker match `semTools` reference on fixtures; an engineered near-redundant pair (r² ≈ .80) passes F–L but trips the HTMT flag/fail bands exactly per PB-11 (FR-703).
- AT-M10-3: CMB — CLF/marker comparison flags a fixture with injected method variance; Harman alone passing does not mark PB-12 complete (FR-704).
- AT-M10-4: deletion protected path — candidate yields Recommendation only; with permit token: one-at-a-time with full re-estimation between deletions (call-sequence asserted), dual trigger enforced (statistical signal alone insufficient), three-item floor and two-item deletion-lock enforced, before/after audit emitted, validated-instrument deviation flagged (FR-705–708).
- AT-M10-5 (absence): batch deletion has no code path (FR-706).
- AT-M10-6: respecification — cross-construct MI suggestions filtered out; within-construct applied one-at-a-time in MI order; cap from policy stops at 3; each logged with MI + EPC + rule (FR-709).

---

## M11 — structural-effects  *(TC-11a structural · TC-11b effects)*

**Purpose.** Structural estimation and fit reporting per PB-15/16; bootstrapped mediation/moderation with Zhao–Lynch–Chen classification per PB-17; higher-order carry recorded.

**Maps to:** `stats/structural`, `stats/effects`.

**Traces.** FR-801–803; PB-15–17.

**Acceptance tests.**
- AT-M11-1: fit indices (χ², χ²/df, CFI, TLI, RMSEA+CI, SRMR) match lavaan reference outputs on the benchmark example; band evaluation recorded as `report`, never mutating the model (FR-801, PB-15).
- AT-M11-2: bootstrap effects reproduce a published mediation example's CIs within tolerance at fixed seed; resamples read from policy (FR-802, FR-1502).
- AT-M11-3: classification — five fixtures (complementary, competitive, indirect-only, direct-only, no-effect) each classified correctly; every hypothesized indirect effect receives a classification entry (PB-17).
- AT-M11-4: hypothesis matrix — verdicts follow PB-16 significance rule incl. marginal-p = not supported; matrix rows carry statistic IDs for every number (FR-1103 backbone, FR-1003-adjacent).
- AT-M11-5: `structural_carrier` from the contract (full hierarchy vs latent scores) demonstrably changes the fitted model and is recorded with rationale (FR-803).

---

## M12 — robustness-verify

**Purpose.** Alternative-model comparison and achieved power; the independent Python verification (semopy on selected estimates, descriptives, structure) within the certified parity map; tolerance/halt logic; **plus** the benchmark replication runner (FR-1502) and the reference-comparison builder (FR-1503).

**Maps to:** `stats/robustness`, `verify/*`, `tests/benchmark/`.

**Traces.** FR-901–903; FR-402; FR-1502/1503.

**Acceptance tests.**
- AT-M12-1: ≥1 alternative model estimated and compared on fit + information criteria; comparison recorded under `robustness.alternatives` (FR-901).
- AT-M12-2: parity — within-tolerance fixture passes; beyond-tolerance-but-below-halt flags with scope named; beyond halt-multiplier → `HALTED_VERIFICATION` with per-estimate diff (FR-902/903).
- AT-M12-3: out-of-parity scopes are declared in FLAGS, never force-compared — fixture with a known non-parity feature (e.g., WLSMV) produces the declaration path (FR-903).
- AT-M12-4: benchmark runner replicates the published worked-example set end-to-end within tolerances and writes the parity map consumed by AT-M12-2 (FR-1502).
- AT-M12-5: reference-comparison builder consumes a reference set + results store and emits a schema-valid report with all entries `unresolved` by default and correct deltas (FR-1503).

---

## M13 — narrate  *(Stage 1B begins)*

**Purpose.** Node B reference-based drafting per the playbook chapter structure; render-time numeric injection; the checker that fails unresolved numbers and unsupported/inconsistent claims.

**Maps to:** `narrate/*`.

**Traces.** FR-1002–1005; PB-20.

**Acceptance tests.**
- AT-M13-1: draft contains statistic references only; a fixture draft with one free-text number fails the checker naming the offending span (FR-1002/1003).
- AT-M13-2: rendered chapter — every number resolves to a store ID; rounding per policy; prose/table consistency check catches a seeded H3a-style contradiction (verdict says unsupported, prose implies supported) (FR-1003).
- AT-M13-3: chapter structure conforms to the playbook order; all hypotheses present including unsupported ones — omission fails PB-20 (FR-1004).
- AT-M13-4 (allowlist): Node B input surface excludes raw data by construction; enumeration test (FR-1005).

---

## M14 — package

**Purpose.** APA tables (DOCX/XLSX) and figures; the SPSS/AMOS validation pack with crosswalk; compliance checklist, AI-use disclosure, supervisor pack; final archive copy-out.

**Maps to:** `package/*`.

**Traces.** FR-1104–1108; FR-1101–1103 assembly; PB-21.

**Acceptance tests.**
- AT-M14-1: every `/reporting/table_set` entry produced or explicitly marked N/A with reason; missing entry fails PB-21 (FR-1104).
- AT-M14-2: SPSS/AMOS pack — cleaned dataset imports into SPSS format readers; covariance/correlation matrices numerically match the results store; crosswalk table maps every pack element to its Burhān source (FR-1105).
- AT-M14-3: disclosure and supervisor pack generated from run artifacts only (no free-text numbers — same checker reused) and contain the mandated sections (FR-1107/1108).
- AT-M14-4: package stage never imports statistical modules — import-graph test (AD-08).
- AT-M14-5: on COMPLETED, `outputs/` mirrors the sealed `runs/<ts>/package/` exactly (hash compare) (FR-1403).

---

## Cross-Module Integration Tests (owned by the plan's milestone gates)

- IT-1 *Pipeline dry run:* stubbed LLM nodes + golden data → COMPLETED end-to-end; compliance checklist covers PB-01..PB-21 (Stage-1A exit uses PB-01..19).
- IT-2 *Rerun identity on a full run* (NFR-101 at system level).
- IT-3 *Boundary run:* under-powered fixture → METHOD_ADVISORY → `COMPLETED_TO_BOUNDARY` with defensible-scope package (FR-403/1203).
- IT-4 *Certification gates green:* golden 100%, benchmark within tolerance, parity map written (FR-1501/1502/1504).

---

## Traceability closure

Every FR-100..FR-1500 and NFR appears in at least one module trace above; `11_CERTIFICATION_PLAN.md` binds AT/IT identifiers to the certification gate, and `12_DBA_VALIDATION_PROTOCOL.md` consumes M12's reference-comparison builder. Contracts in `09_task_contracts/` restate their module's scope, traces, and acceptance tests verbatim — the contract adds delivery detail, never new scope.
