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
| TC-08c | 7e97d6e | 2026-07-03 | APPROVE | Golden certification suite accepted; 14-class defect matrix pinned to code, adversarial first-link attribution, CI regression gate live (run 28656914431), M08/M3 exit evidence complete. |
| TC-09 | 43b8f52 | 2026-07-03 | APPROVE | Power-assumptions accepted; AT-M09-1..5 green, typed Monte Carlo worker-result validation, E-R3/E-R4 governed resolutions, CI run 28673797357 green. |
| TC-10a | d4b38b2 | 2026-07-03 | APPROVE | Measurement CFA/validity/CMB accepted; AT-M10-1..3 green, semTools reliability pins, typed second-order reliability guard, CI runs 28682109548/28682111052 green. |
| TC-10b | 5a64a18 | 2026-07-03 | APPROVE | Deletion protocol and respecification accepted; invalid attestations and empty permit rules guarded, AT-M10-4..6 green, CI runs 28683917143/28683918295 green. |
| TC-11a | 06f0542 | 2026-07-03 | APPROVE | Structural estimation accepted; AT-M11-1/5 green, typed fit/path/R² validation, carrier semantics, CI runs 28685721644/28685722979 green. |
| TC-11b | 7449959 | 2026-07-04 | APPROVE | Effects and hypothesis matrix accepted; no-direct-edge engine benchmark, paths/sums validation, store-backed matrix IDs, CI runs 28696426699/28696427326 green. |
| TC-12 | 00bcef2 | 2026-07-04 | APPROVE | Robustness-verify and benchmark/reference tooling accepted; AT-M12-1..5 green, typed malformed-input halts across independent/parity/reference lanes, PB-18 floor >= 1, CI runs 28702607796/28702608373 green. |
| TC-15 | a5fa7a1 | 2026-07-05 | APPROVE | Production Stage-1A pipeline wired into the orchestrator (13-stage DAG to COMPLETED under stubbed nodes); Stage-1B certification pass-through; PB-12/PB-14 data-conditioned; sealed-base rerun (NFR-101) and actual-source manifest hashes (NFR-102); AT-M15-1..6 green, CI runs 28742917432/28742940200 green. |
| TC-16 | 8aa9d59 | 2026-07-06 | APPROVE | Live-provider run path accepted; pre-DAG extract+confirm with un-bypassable glance token, DOCX ingestion, LLM archive/replay for byte-identical rerun (NFR-101), headless Stage-1A, sealed item-10 reference comparison via a live-only terminal-stage wrapper (fixed 13-stage PIPELINE unchanged; orchestrator/manifest untouched), AT-M16-1..8 green, CI runs 28769641974/28769643275 green. |
| M6 §7 | 19258b9 | 2026-07-06 | APPROVE | Node A adapter correction (§7 engine_or_policy_correction, researcher-governed change control): unwrap a whole-response yaml/yml/bare markdown code fence before the FR-205/FR-203 checks (other language tags fail FR-203; a fenced AMBIGUOUS: still halts FR-205); Node-A-only max_tokens=16384, all other nodes retain the 8192 default. Scope = these two adapter defects; certification path, statistics, schemas, and governed docs untouched. 1087 tests green (0 failures), coverage 99%; PR #19 CI 28792346415 green; squash-merged 520bc29. |
| M6 §7 (Node A schema-contract) | 899fc3d | 2026-07-07 | APPROVE | Node A prompt correction (§7 engine_or_policy_correction, researcher-governed change control): prompts/node_a/v1.md now carries the study_config output contract - the 11 allowed top-level keys (extras forbidden), per-item scale.labels string arrays (no numeric-keyed anchors, no nested instrument.scale_range), out-of-model -> data.ignored_item_columns, and a no-reference_comparison / no-retained-subset prohibition (FR-202); fixes the live DBA extraction halt "non-string dict key in canonical payload" (HALTED_INTEGRITY, exit 10). Scope = prompts/node_a/v1.md + tests; schema, certification path, statistics, and governed docs untouched. 1095 tests green (0 failures), coverage 99%; PR #20 CI 28839850485 green; squash-merged 994c71e. |
| M6 §7 (Node A provenance injection) | 39cc142 | 2026-07-07 | APPROVE | Node A combined engine+prompt correction (§7 engine_or_policy_correction, researcher-governed change control): prompts/node_a/v1.md carries the full per-block study_config field contract (model classifies by role only — model.paths/edges/relationships forbidden, structural edges route to hypotheses; anchors -> scale.labels; out-of-model -> ignored_item_columns) and instructs Node A to omit meta.source_documents + methodology.playbook_id/version and never fabricate a hash; the engine injects those authoritative, non-LLM-derivable fields (real sha256 of resolved inputs + governed playbook id/version via _governed_playbook_identity) into NodeA.extract BEFORE validate_and_build, threaded through Contract -> production_registry so --confirm/rerun replays complete; provenance is authored once (live_extract) then read forward — live_confirm from the persisted glanced config, live_rerun from the sealed run contract — never recomputed from the mutable bundle (preserves the glance boundary + NFR-101 rerun byte-identity). Scope = prompt + node_a/stage_1a/registry/live engine + tests; schema, loader, certification, statistics, and governed docs untouched. 1120 tests green (0 failures), coverage 99%; PR #21 CI 28864324661 green; squash-merged bd25d4c. |

**Milestone gate records** (researcher sign-offs; see plan ★/★★):

| Gate | Date | Signed by | Evidence |
|---|---|---|---|
| M5 certification | 2026-07-05 | Researcher (Salim Al Barami) | CERTIFICATION_REPORT.md GATE PASS @ 20da2db |
| M6 DBA validation | — | — | reference comparison, unresolved = 0 |
| M7 go-live | — | — | 14_GO_LIVE_CHECKLIST executed |
