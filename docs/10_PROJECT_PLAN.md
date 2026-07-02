# Burhān — Phase 1 Project Plan (docs/10_PROJECT_PLAN.md)

**Scope:** Phase 1 — CB-SEM v1 Core Release
**Status:** For review
**Governed by:** `08_BUILD_SPEC.md` (modules, contracts, acceptance tests), `15_ENGINEERING_STANDARDS.md` (workflow), Concept §6/§14/§15 (staging, acceptance, validation-first).

**Planning unit.** Progress is measured in **approved contracts and passed gates, not calendar time**. The build is serial by protocol (one active contract; Codex APPROVE gates the next), so the plan fixes *order and exit criteria* and deliberately makes no duration promises. `SIGNOFFS.md` plus the doc-index status column are the single source of progress truth.

---

## Milestone Map

```
M0 scaffold ─ M1 foundation ─ M2 contract&gates ─ M3 prep core ─ M4 stats core
                                                        │
                                          M5 certification (Stage 1A complete) ★
                                                        │
                                          M6 DBA validation run ★★
                                                        │
                                          M7 reporting layer & go-live ★★
```
★ = Codex gate + researcher sign-off · ★★ = researcher gate (supervisor where applicable)

| MS | Name | Contracts | Gate instrument | Gate owner |
|---|---|---|---|---|
| M0 | Repository scaffold & environment | — | doctor + CI skeleton | Codex |
| M1 | Foundation & governance | TC-01..04 | module ATs + stub-pipeline smoke | Codex |
| M2 | Contract & gates | TC-05..07 | module ATs + Gate-1 live demo | Codex |
| M3 | Preparation core | TC-08a..c | golden suite (FR-1501 half of certification) | Codex |
| M4 | Statistical core | TC-09, 10a/b, 11a/b | known-answer + published-example ATs | Codex |
| M5 | Certification — Stage 1A complete | TC-12 | `11_CERTIFICATION_PLAN.md` executed; IT-1..4 | Codex → **Researcher sign-off** |
| M6 | DBA validation run | — (operates the system) | `12_DBA_VALIDATION_PROTOCOL.md`; unresolved = 0 | **Researcher (+supervisor)** |
| M7 | Reporting layer & go-live | TC-13, TC-14 | `14_GO_LIVE_CHECKLIST.md`; Concept §14 acceptance | Codex → **Researcher go-live** |

---

## M0 — Repository Scaffold & Environment

**Entry.** Wave 1–3 documents approved; GitHub repository created.
**Work.** Initialize the repo per `03_ARCHITECTURE.md` §10; commit docs 00–08 + 15, CLAUDE.md, AGENTS.md, schemas, playbook, policy/registry, prompt-template stubs, config examples; bootstrap the workstation per `04_ENVIRONMENT_AND_STACK.md` §8; create the studies root and stage the DBA study inputs (U1–U4) into `studies/dba-validation-study/inputs/`; CI skeleton (ruff, mypy, pytest, schema-validation job reproducing the Wave-2 checks).
**Exit (DoD).** `burhan doctor` green on the workstation (doctor may ship as a standalone script pre-M04 and be absorbed by TC-04) · CI green on the empty-src skeleton · `.gitignore` proves studies-content exclusion (standards §7) · doc-index statuses updated.

## M1 — Foundation & Governance (TC-01..TC-04)

**Entry.** M0 exit.
**Work.** core-foundation → governance → playbook-engine → orchestrator/CLI/R-harness, in contract order.
**Exit (DoD).** All module ATs green (AT-M01-1..6, AT-M02-1..6, AT-M03-1..4, AT-M04-1..6) · stub-pipeline smoke: state machine traverses S0→S10 with stub stages; every halt class reachable by fault injection · rerun byte-identity on a stub run (AT-M04-4) · coverage gates met incl. 100% modules.

## M2 — Contract & Gates (TC-05..TC-07)

**Entry.** M1 exit.
**Work.** ingest-crosswalk → Node A (+adapter base, lineage validation) → Node C gates.
**Exit (DoD).** Module ATs green · **live demonstration:** fixture study document + fixture export → crosswalk → Node A contract → V1–V7 → Gate 1 APPROVE, then the seeded-corruption set each REJECTed with correct fixes (AT-M07-1) · autonomy boundary proven with real gate in the loop (stdin-closed run past G1) · allowlist rejection tests in CI permanently.

## M3 — Preparation Core (TC-08a, TC-08b, TC-08c)

**Entry.** M2 exit.
**Work.** Python prep + N-chain + invariants → R prep + reconciler → golden-dataset generator + suite.
**Exit (DoD).** **Golden certification half passes:** 100% detection of all defined planted defects; zero unexplained dual-path cell differences; N-chain exact on golden and adversarial fixtures; absence tests (FR-505) in CI · AT-M08-1..8 green.

## M4 — Statistical Core (TC-09, TC-10a/b, TC-11a/b)

**Entry.** M3 exit.
**Work.** power/assumptions/estimator → measurement (CFA/validity/CMB, then deletion+respecification) → structural, then effects.
**Exit (DoD).** AT-M09-1..5, AT-M10-1..6, AT-M11-1..5 green — including the MacCallum table replication, published higher-order and mediation examples within tolerance, the HTMT-vs-F–L near-redundancy trap, the deletion protocol under permit token, and the marginal-p rule in the hypothesis matrix.

## M5 — Certification: Stage 1A Complete (TC-12) ★

**Entry.** M4 exit; **`11_CERTIFICATION_PLAN.md` authored and approved (Wave-4 document checkpoint — hard precondition).**
**Work.** robustness + verification + benchmark runner + reference-comparison builder; then execute the certification plan end-to-end.
**Exit (DoD).** AT-M12-1..5 green · benchmark replication within tolerance across measurement/structural/mediation; certified parity map written and documented (FR-1502) · IT-1 dry run COMPLETED with compliance checklist covering PB-01..19 · IT-2 full-run rerun identity · IT-3 boundary run produces METHOD_ADVISORY + `COMPLETED_TO_BOUNDARY` package · IT-4 certification gates green and archived as regression (FR-1504) · **Researcher sign-off recorded: the engine is certified to touch real data.**

## M6 — DBA Validation Run ★★

**Entry.** M5 sign-off; **`12_DBA_VALIDATION_PROTOCOL.md` authored and approved (Wave-4 checkpoint);** U1–U5 staged; reference set (manual results extracted from the paper) prepared per the protocol.
**Work.** Operate the system: Node A contract from the DBA study document (designed instrument, FR-202) → optional 5-minute contract glance → Gate 1 → headless Stage-1A run → reference comparison built (M12 tool) → divergence investigation and classification per protocol — **no side presumed correct**.
**Exit (DoD).** Stage-1A output set produced (Concept §15 minimum deliverables) · reference comparison report complete with **unresolved = 0** · every `engine_or_policy_correction` fixed and re-run; every `manual_weakness` documented (these are also the evidence base for the supervisor's construct/item revision request) · policy/playbook version changes, if any, recorded via change control · **Researcher (+supervisor where applicable) sign-off.**

## M7 — Reporting Layer & Go-Live (TC-13, TC-14) ★★

**Entry.** M6 sign-off.
**Work.** narrate (Node B + renderer + checker) → package (tables, SPSS/AMOS pack, governance docs) · full run on the DBA study producing the complete output package · finalize `13_RUNBOOK.md` alongside · execute `14_GO_LIVE_CHECKLIST.md`.
**Exit (DoD).** AT-M13-1..4, AT-M14-1..5 green · complete output package on the DBA study incl. findings chapter, SPSS/AMOS pack, compliance checklist, AI-use disclosure, supervisor pack — with Gate 2 passed and the number-resolution checker green · Concept §14 Phase-1 acceptance list verified item-by-item · runbook proven by executing new-study onboarding from it alone (NFR-801) · **go-live declared; `hayat-tayyibah-2026` onboarding unblocked.**

---

## Document Checkpoints (Wave 4–5 interleave)

| Before | Author & approve |
|---|---|
| M5 gate execution | `11_CERTIFICATION_PLAN.md` |
| M6 entry | `12_DBA_VALIDATION_PROTOCOL.md` (incl. tolerance table + reference-extraction worksheet) |
| M7 exit | `13_RUNBOOK.md` (drafted during M1–M6, proven at M7) · `14_GO_LIVE_CHECKLIST.md` |

## Working Cadence & Change Control

- **One active contract**; Codex issues the next only on APPROVE (AGENTS.md). REJECT cycles stay inside the contract.
- **Governed-document changes** (concept, requirements, architecture, schemas, playbook, policy, registry, build spec, contracts) are researcher-only, made as explicit versioned edits between contracts — never inline during one. Hash changes propagate via the manifest (NFR-102).
- **Escalations** land with the researcher per AGENTS.md; a blocked contract halts the lane rather than improvising.

## Risk Watchlist (managed at milestone gates)

1. **R↔Python parity narrower than hoped** → parity map declares scope honestly; FLAGS not force-fits (FR-903); revisit tolerances at M5 only.
2. **LLM extraction quality on the real DBA document** → M2's corruption-set demo plus data-dictionary cross-check; contract glance remains available; hard-fail semantics protect M6.
3. **Golden-suite blind spots** → defect matrix in doc 11 reviewed against the DBA raw file's known pathologies (progress-based partials, consent rows, embedded item codes) before M3 closes.
4. **Reference-set extraction errors** (from the paper) → doc 12 worksheet requires dual-source values (paper table + text) and marks single-source values as low-confidence.
5. **Scope pressure to start Hayat Tayyibah early** → structurally blocked: onboarding requires M7 go-live per the checklist.
