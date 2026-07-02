# Burhān — Technical Architecture (docs/03_ARCHITECTURE.md)

**Scope:** Phase 1 — CB-SEM v1 Core Release
**Status:** For review
**Governed by:** `01_CONCEPT.md` (doctrine) and `02_REQUIREMENTS.md` (binding requirements; FR/NFR references below are to that document).

---

## 1. Architectural Overview

Burhān is a **locally executed, stage-gated, typed pipeline**. A Python orchestration core advances a run through a fixed DAG of stages; every stage consumes schema-validated, immutable artifacts and emits schema-validated, immutable artifacts plus provenance entries. Statistical truth is computed exclusively by deterministic engines — **R (authoritative)** and **Python (independent verification)** — invoked as isolated workers. Three bounded LLM adapters (Nodes A, B, C) handle document understanding, narration, and artifact audit; they sit behind hard input allowlists and schema validation and are architecturally incapable of touching respondent-level data or emitting numbers into the results store (FR-206, FR-1005, NFR-401/402).

Control flow is static: no dynamic planning, no agentic loops beyond the bounded Gate retry. Autonomy is a property of the *policy engine*, not of model improvisation (FR-306, FR-1201).

---

## 2. Key Architecture Decisions

- **AD-01 — Orchestration is a custom typed stage pipeline, not an agent framework.** The DAG is fixed, control flow is fully static, and byte-reproducibility (NFR-101) is a hard requirement; a hand-rolled state machine over pydantic-validated artifacts is simpler to test and freeze than LangGraph, whose value (dynamic agentic control) this design deliberately excludes. The bounded Node C retry loop is trivial without a graph framework.
- **AD-02 — R is invoked as file-based `Rscript` workers.** Each statistical call is a subprocess with JSON-file input/output contracts inside the run directory, pinned via `renv`. File-based handoff makes every intermediate inspectable and archivable (NFR-301) and isolates R state between calls.
- **AD-03 — No partial resume.** A failed run is fixed (policy/contract/data) and re-executed in full. Full re-execution is cheap at this scale (NFR-501), and resume logic is the enemy of bit-identical reproducibility (NFR-101).
- **AD-04 — LLM nodes are allowlisted adapters.** Each node has a declared input artifact set (Node A: study document text, data dictionary; Node B: results store, contract, playbook chapter spec; Node C: artifacts under audit plus their sources). Anything else is rejected at the adapter boundary. Providers are configured per node in `04_ENVIRONMENT_AND_STACK.md`; config validation fails if Node A and Node C resolve to the same model lineage (FR-304). Prompt templates are versioned files, hashed into the run manifest.
- **AD-05 — Results store is append-only with hierarchical statistic IDs.** JSONL + index; single writer per stage; IDs like `measurement.loadings.first_order.R_TI.R9.std`. Node B consumes IDs, never values (FR-1001/1002).
- **AD-06 — All inter-stage handoff is on disk inside the run directory.** Auditability and re-run identity outrank in-memory speed.
- **AD-07 — Parallelism only where bit-reproducible.** Bootstrap and Monte Carlo run parallel only under fixed per-worker seed derivation verified reproducible in certification; otherwise serial. Overnight budget (NFR-501) provides the headroom.
- **AD-08 — Document/table generation is isolated in the packager.** `python-docx`/`openpyxl` rendering never imports from, or feeds back into, statistical modules.

---

## 3. Component Map

```
burhan (engine)
├── cli/                    burhan run <study-dir> | rerun <run-dir> | certify
├── core/
│   ├── orchestrator        stage registry, state machine, gate control
│   ├── artifacts           pydantic models + schema validation (05_schemas)
│   ├── policy              decision_policy loader/evaluator, decision logger
│   ├── registry            Protected Decisions Registry enforcement (FR-1202)
│   ├── playbook            playbook loader/validator, compliance tracker (FR-1301/1302)
│   ├── provenance          sanad log appender, FLAGS/DECISION_LOG writers
│   └── manifest            seeds, hashes, environment freeze, run archive
├── contract/
│   ├── crosswalk           export-header → item-code mapper (FR-103)
│   ├── node_a              LLM adapter: document → study_config (FR-201..206)
│   └── validators          schema + data-dictionary cross-check (FR-203/204)
├── review/
│   └── node_c              LLM adapter: Gate 1 / Gate 2 audits (FR-301..305)
├── prep/
│   ├── r_impl              R preparation implementation        (FR-501)
│   ├── py_impl             Python preparation implementation   (FR-501)
│   ├── reconciler          cell-level diff, halt on mismatch   (FR-501)
│   ├── invariants          post-prep assertions                (FR-507)
│   └── n_chain             exact N reconciliation accountant   (FR-506)
├── stats/                  R authoritative workers (lavaan/semTools/simsem)
│   ├── power               a priori + achieved (FR-401/402)
│   ├── assumptions         Mardia, VIF, Mahalanobis, estimator determination (FR-601..603)
│   ├── measurement         CFA incl. higher-order, validity, CMB, deletion protocol (FR-700)
│   ├── structural          fit, paths, R², respecification control (FR-801, FR-709)
│   ├── effects             bootstrap mediation/moderation (FR-802)
│   └── robustness          alternative models (FR-901)
├── verify/
│   ├── py_stats            semopy/pandas verification calls (FR-902)
│   └── parity              certified parity map + tolerance checks (FR-902/903)
├── results/
│   └── store               append-only statistic store + ID resolver (FR-1001)
├── narrate/
│   ├── node_b              LLM adapter: reference-based drafting (FR-1002/1004/1005)
│   ├── renderer            render-time numeric injection
│   └── checker             number-resolution + claim-consistency gate (FR-1003)
└── package/
    ├── tables              APA DOCX/XLSX tables, figures (FR-1104)
    ├── spss_amos           validation pack + crosswalk (FR-1105)
    └── governance_docs     compliance checklist, disclosure, supervisor pack (FR-1106..1108)

studies/<study>/            inputs/ config/ runs/ outputs/   (engine-external; FR-1402)
```

---

## 4. Pipeline DAG & Run State Model

**Stages (fixed order):**

```
S0 INGEST          crosswalk, file integrity, structural match        (FR-101..104)
S1 CONTRACT        Node A → study_config + validators                 (FR-200)
G1 GATE-1          Node C audit → validated study contract            (FR-301,306)
S2 POWER           a priori power & adequacy                          (FR-400)
S3 PREP            dual-path preparation → reconciler → invariants    (FR-500)
S4 ASSUMPTIONS     diagnostics + estimator determination              (FR-600)
S5 MEASUREMENT     CFA/higher-order, validity, CMB, deletion protocol (FR-700)
S6 STRUCTURAL      fit, paths, respecification control                (FR-801,709)
S7 EFFECTS         bootstrapped mediation/moderation                  (FR-802)
S8 ROBUSTNESS      alternatives, verification, achieved power         (FR-900,402)
S9 NARRATE         Node B draft → renderer → checker                  (FR-1000)
G2 GATE-2          Node C audit of draft vs results store             (FR-302)
S10 PACKAGE        tables, packs, governance docs, archive seal       (FR-1100)
```

**Run states:** `PENDING → RUNNING(stage) → COMPLETED` with terminal exceptions `HALTED_INTEGRITY` (FR-1204), `HALTED_VERIFICATION` (FR-903), `HALTED_GATE` (FR-303), and `COMPLETED_TO_BOUNDARY` (Method Advisory issued; package produced up to the defensible boundary, FR-1203/403). Stage transitions, timings, and outcomes are written to the manifest (NFR-502).

**Autonomy boundary:** interactive input is possible only before/at G1 (optional contract glance); from G1-pass to terminal state the orchestrator exposes no input channel (FR-306, FR-1401).

**Artifact rule:** artifacts are written once, hashed, and never mutated; downstream stages reference by path+hash. Every stage appends provenance entries (NFR-301) and its compliance-checklist rows (FR-1106).

---

## 5. LLM Node Integration

| | Node A (Contract) | Node B (Narration) | Node C (Muḥāsaba) |
|---|---|---|---|
| Inputs (allowlist) | study document text; data dictionary | results store; validated contract; playbook chapter spec | artifact under audit + its source artifacts |
| Output | `study_config.yaml` (schema-validated) | draft with statistic references only | verdict: approve / reject-with-exact-fixes (schema-validated) |
| Forbidden | raw data files | raw data; free-text numbers | computing statistics; editing artifacts |
| Provider | configured lineage L1 | any configured | configured lineage L2 ≠ L1 (validated at startup) |

Adapters run with deterministic settings where the provider supports them; prompt template version + hash enter the manifest. Gate retry: reject → author node revises → re-audit, bounded by `policy.gates.max_retries`; exhaustion → `HALTED_GATE` (FR-303). Node outputs failing schema validation count as rejects.

---

## 6. R ↔ Python Interop Contract

Every statistical call is: orchestrator writes `call_<id>.input.json` → spawns `Rscript workers/<module>.R call_<id>` → worker writes `call_<id>.output.json` + optional artifacts → orchestrator validates output schema. Workers are stateless; the analytical dataset is passed by path (parquet/feather + CSV mirror for the archive). R environment is `renv`-locked; worker startup asserts package versions against the lockfile and aborts on drift (NFR-101/102). Worker stderr is captured to the run log; nonzero exit or schema-invalid output → `HALTED_INTEGRITY` with the captured report (NFR-201).

The verification path mirrors the same contract in-process (Python) and writes `verify_<id>.output.json`; the parity module compares authoritative vs verification outputs within the certified tolerance map and emits per-scope pass/flag/halt (FR-902/903).

---

## 7. Failure & Halt Semantics

| Class | Trigger | Behavior |
|---|---|---|
| `POLICY_RESOLVED` | any operational judgment | apply rule, log rule ID, continue (FR-1201) |
| `FLAG` | noteworthy but defensible condition | record in FLAGS with severity, continue (FR-903) |
| `ADVISORY_STOP` | evidence challenges approved method | emit METHOD_ADVISORY, complete defensible scope, `COMPLETED_TO_BOUNDARY` (FR-1203) |
| `HALTED_INTEGRITY` | data–document mismatch, invariant fail, N-chain fail, worker fault | stop at stage; machine- and human-readable report; partials preserved marked non-final (FR-1204, NFR-202) |
| `HALTED_VERIFICATION` | dual-path or parity breach beyond tolerance | stop with discrepancy report (FR-501, FR-903) |
| `HALTED_GATE` | Node C retries exhausted | stop with final verdict + fix list (FR-303) |

No other failure classes exist; anything unclassifiable is `HALTED_INTEGRITY` by definition (NFR-201).

---

## 8. Results Store

Append-only JSONL with a derived index. Entry: `{id, value, se, ci_low, ci_high, unit, n, stage, engine, playbook_step, hash}`. ID grammar: `<stage>.<family>.<construct|path>[.<item>][.<variant>]` — e.g., `structural.path.READINESS→PEOU.std`, `effects.indirect.READINESS→INT.boot_ci`. Writers: statistical stages only, single writer per stage window. Readers: renderer, checker, packager, verification. The checker resolves every number in the rendered draft back to an ID and fails on any orphan or on claim/verdict inconsistency (FR-1003).

---

## 9. Run Archive Layout

```
studies/<study>/runs/<UTC-timestamp>/
├── manifest.json            seeds, hashes (config/policy/playbook/prompts/lockfiles), versions, timings
├── contract/                study_config.yaml, crosswalk.json, gate1_verdicts/
├── prep/                    r/, py/, reconciliation.json, n_chain.json, invariants.json
├── stats/                   call_*.{input,output}.json per stage
├── verify/                  verify_*.output.json, parity_report.json
├── results/                 results.jsonl, index.json
├── narrate/                 draft.refs.md, rendered.md, checker_report.json, gate2_verdicts/
├── logs/                    run.log, stage timings
└── package/                 → copied to studies/<study>/outputs/ on COMPLETED
    ├── tables/ figures/ spss_amos/
    ├── FINDINGS_CHAPTER.docx  SUPERVISOR_REVIEW_PACK.docx
    ├── METHOD_COMPLIANCE_CHECKLIST.md  AI_USE_DISCLOSURE.md
    ├── DECISION_LOG.md  FLAGS.md  [METHOD_ADVISORY.md]
    └── PROVENANCE.jsonl
```

`burhan rerun <run-dir>` re-executes from `manifest.json` and asserts byte-identity of regenerated artifacts (NFR-101, FR-1403).

---

## 10. Repository Layout

```
burhan/
├── CLAUDE.md  AGENTS.md  README.md
├── docs/                    00–15 per the documentation index
├── playbooks/               CB_SEM_PLAYBOOK_v1.0.yaml (+ schema)
├── policy/                  decision policy template + protected registry (+ schemas)
├── schemas/                 study_config / results_store / provenance / manifest / policy / registry
├── src/burhan/              components per §3
├── workers/r/               Rscript workers + renv.lock
├── prompts/                 node_a/ node_b/ node_c/ (versioned templates)
├── tests/                   unit/ fixtures/ golden/ benchmark/
└── pyproject.toml  uv.lock
studies/                     engine-external (FR-1402)
```

---

## 11. Determinism & Security Controls

- **Seeds:** one master seed per run (manifest) → HKDF-derived per-stage and per-worker seeds; R and Python RNGs set explicitly per call.
- **Pinning:** `uv.lock` (Python) + `renv.lock` (R); startup asserts both; hashes in manifest (NFR-102).
- **Network:** compute stages make no network calls; only LLM adapters may egress, to configured providers, and their inputs are the allowlisted artifacts only — enforced in the adapter, not by convention (NFR-401). Secrets via environment, never in repo or manifest.
- **Immutability:** run directory files are written-once; the seal step records the final hash tree.

---

## 12. Component → Requirement Trace

CLI/orchestrator → FR-306, FR-1204, FR-1401/1403, NFR-201/202/501/502 · contract/* → FR-100/200 · review/node_c → FR-300 · prep/* → FR-500, NFR-101 · stats/* → FR-400/600/700/800/900 · verify/* → FR-902/903 · results/store → FR-1001 · narrate/* → FR-1002..1005 · package/* → FR-1104..1108 · core/policy+registry → FR-1201..1204 · core/playbook → FR-1301..1304 · core/provenance+manifest → FR-1109, NFR-100/300 · tests/golden+benchmark → FR-1501..1504, NFR-600.
