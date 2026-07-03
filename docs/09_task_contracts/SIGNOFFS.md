# Burhān — Contract Sign-off Ledger (docs/09_task_contracts/SIGNOFFS.md)

Single source of progress truth (10_PROJECT_PLAN.md). One line per verdict; APPROVE unlocks dependents. Format:

`| contract | commit | date (UTC) | verdict | note |`

| Contract | Commit | Date | Verdict | Note |
|---|---|---|---|---|
| — | — | — | — | ledger opens at M0 |
| M0 | 39a7719 | 2026-07-02 | APPROVE | Repository scaffold and governed-document gate verified. |
| TC-01 | 23e6efd | 2026-07-02 | APPROVE | Core foundation accepted; E2 doctor deferral applies until TC-04. |
| TC-02 | 1744ec6 | 2026-07-02 | APPROVE | Governance accepted; protected boundary enforced at load, cross-check, and guard. |
| TC-03 | d23a32f | 2026-07-02 | APPROVE | Playbook engine accepted; compliance replay cannot bypass the FR-1106 store gate. |
| TC-04 | 8a99436 | 2026-07-02 | APPROVE | Orchestrator/CLI/R harness accepted; real R, lintr, zero-skip suite, and doctor green. |
| TC-05 | be136ee | 2026-07-02 | APPROVE | Ingest crosswalk accepted; ragged headers halt typed and all gates green. |
| TC-06 | 5b9e48a | 2026-07-02 | APPROVE | Node A contract accepted; typed llm.yaml validation, dictionary polarity, and all gates green. |
| TC-07 | 3e05188 | 2026-07-03 | APPROVE | Node C gates accepted; schema-valid Gate 2 evidence, strict duplicate-key/blank-fix verdicts, bounded retry loop, all gates green. |
| TC-08a | 5b35d12 | 2026-07-03 | APPROVE | Python prep accepted; policy-driven screening, exact case-level N-chain (same-link double-counts halt), seven invariants, golden core, all gates green. |
| TC-08b | 2e57a1f | 2026-07-03 | APPROVE | R prep + reconciler accepted; live cell-for-cell parity at tolerance 0, typed divergence halts naming row/column, lintr clean, all gates green. |

**Milestone gate records** (researcher sign-offs; see plan ★/★★):

| Gate | Date | Signed by | Evidence |
|---|---|---|---|
| M5 certification | — | — | 11_CERTIFICATION_PLAN execution report |
| M6 DBA validation | — | — | reference comparison, unresolved = 0 |
| M7 go-live | — | — | 14_GO_LIVE_CHECKLIST executed |
