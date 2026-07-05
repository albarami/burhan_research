# Burhān — DBA Validation Protocol (docs/12_DBA_VALIDATION_PROTOCOL.md)

**Scope:** Milestone M6 gate instrument — the first live run, against the researcher's completed DBA study
**Status:** For review (Codex), then governs M6 execution
**Governed by:** Concept §15 (validation-first doctrine), `10_PROJECT_PLAN.md` §M6, `schemas/reference_comparison.schema.json`, and the reference-comparison builder delivered in TC-12.

**What M6 is.** Burhān independently re-analyzes the DBA raw data under the approved playbook and compares its results to the researcher's prior manual analysis. **No side is presumed correct** (Concept §15). The run's purpose is not new findings but certification that the engine can execute, explain, and audit a complete analysis with full provenance — and, as a byproduct, to give the researcher item-level evidence for the construct/item revision the supervisor requested. M6 is signed only when every divergence is resolved: **unresolved = 0**.

**What the engine takes vs. what it does not.** It consumes the study's *approved methodology* — framework, model, structure, the **designed instrument mapping**, and thresholds (all already encoded in `CB_SEM_PLAYBOOK_v1.0` and the study contract). It does **not** consume the manual numeric results and does **not** consume the manually-retained item subset — item retention is re-derived by the pipeline (FR-202), and the manual retained/dropped sets enter the reference set instead (§3, row R). This is why an error in the prior study cannot propagate into the engine; it can only surface as a divergence.

---

## 1. Inputs (staged, engine-external)

At `~/projects/burhan-studies/dba-validation-study/inputs/`:
- **U1** Study document — *Organizational Readiness versus Technical Capabilities* (DOCX). Node A source.
- **U2** Raw survey export — the Qualtrics CSV. Pipeline data.
- **U4** Survey instrument — the pilot survey DOCX, serving as data dictionary.
- **U3 / reference set** — the manual results, transcribed into the reference worksheet (§3) from the paper's tables and text.

## 2. Execution Sequence

1. **Certification precondition:** M5 GATE PASS recorded (SIGNOFFS). M6 does not start otherwise.
2. **Contract extraction:** Node A → `study_config.yaml` for the DBA study (designed instrument, FR-202). Optional researcher 5-minute contract glance.
3. **Gate 1:** Node C audit → validated study contract.
4. **Headless Stage-1A run** on the certified workstation: power → prep (dual-path, FIML, exact N-chain) → assumptions/estimator → measurement (CFA incl. higher-order, validity, CMB, deletion **recommendations only** — policy `preauthorized: false`) → structural → effects → robustness. Produces the results store, decision log, flags, provenance, compliance checklist.
5. **Reference comparison:** the TC-12 builder consumes the results store + the §3 reference set → `REFERENCE_COMPARISON.md` (schema-valid; every row defaults `unresolved`).
6. **Divergence resolution:** each row investigated and classified per §4; resolve to zero.

## 3. Reference-Extraction Worksheet (pre-populated from the paper)

Values transcribed from the researcher's paper for comparison. **Dual-source rule:** where a value appears in both a table and the text, both are checked; single-source values are marked low-confidence and re-verified against the raw run. These are the *manual* figures — the comparison target, **not** ground truth.

### R-A · Sample & data treatment
| Item | Manual value (paper) | Confidence |
|---|---|---|
| Invitations distributed | ~30,000 | text |
| Raw responses | 1,794 | text |
| Completed / retained analytical N | 220 | text + Table 1 |
| Excluded (incomplete) | 1,574 | derived |
| Missing-data treatment | *(paper: iterative refinement; treatment to confirm)* | low — verify |
| Univariate outlier rule | \|z\| > ±3.29 | text |
| Multivariate outlier rule | Mahalanobis D² | text |

> Burhān will apply its policy (≥90% inclusion on model items, FIML, exact N-chain). The **1,794 → 220** chain is a primary comparison locus: the engine independently derives its analytical N and every exclusion count. A mismatch here is expected and informative (the raw file shows 233 fully finished + 16 at 90–99% ≈ 249 eligible before quality screening) — classify per §4, do not force-match.

### R-B · Reliability & convergent validity (retained-model figures)
| Construct | α (paper) | AVE (paper) |
|---|---|---|
| R_TI Technological Infrastructure | 0.905 | *(table)* |
| R_WC Workforce Competencies | *(table)* | *(table)* |
| R_OC Organizational Culture | *(table)* | *(table)* |
| R_LC Leadership Commitment | *(table)* | *(table)* |
| A_PEOU Perceived Ease of Use | 0.953 | 0.806 |
| A_PU Perceived Usefulness | *(table)* | *(table)* |
| A_ATT Attitude toward AI | *(table)* | *(table)* |
| A_INT Intention to Use AI | *(table)* | *(table)* |
| C_TD Data Management Capabilities | 0.949 | 0.760 |
| C_TS Analytics/Infrastructure Capabilities | *(table)* | *(table)* |
| C_T (third capability dimension) | *(table)* | *(table)* |

> Cells marked *(table)* are transcribed from the paper's reliability table at execution (the report generator reads them from the worksheet the researcher completes). The anchors already captured — R_TI α=.905, PEOU α=.953/AVE=.806, C_TD α=.949/AVE=.760 — are the high-confidence comparison points.

### R-C · Discriminant validity
| Item | Manual value | Note |
|---|---|---|
| Method | Fornell–Larcker (squared correlations) | text |
| Highest squared inter-construct correlation | r² = 0.797, **A_ATT ↔ A_INT** | text |
| HTMT | *not reported in manual analysis* | — |

> Burhān adds **HTMT** (playbook PB-11). The ATT↔INT pair (r²=.797) passes Fornell–Larcker but is the prime candidate to trip the HTMT flag/fail band — a known, expected divergence and a direct input to the supervisor's construct-revision question.

### R-D · Model fit (adjusted / final Model 2)
| Index | Manual value (paper) |
|---|---|
| CMIN/DF | *(Table)* — reported adequate |
| CFI | *(Table)* |
| TLI | *(Table)* |
| RMSEA (final Model 2) | 0.079 |
| SRMR | 0.070 |
| Respecification | 1 covariance added (Model 1 → Model 2), MI-ranked, within the study's stated rule |

### R-E · Hypotheses & effects
| Group | Manual verdict (paper) |
|---|---|
| H1, H2 (readiness → adoption vars) | Supported |
| H3a | Not supported *(note: paper text/table inconsistency flagged earlier — verify)* |
| H3b | Supported |
| H4–H6 (capabilities) | Not supported |
| H6a (capabilities → intention, direct) | Marginal at .10, **not supported** at .05 |
| Mediation inference | 5,000 bootstrap samples |

> The **H3a prose/table inconsistency** noted at intake is itself a comparison row: Burhān's statistic-ID-locked reporting cannot produce that contradiction, so the engine's verdict is unambiguous — classify the manual inconsistency accordingly.

### R · Item retention (manual choices → reference only)
| Item | Manual value |
|---|---|
| Manually retained item set per construct | *(from paper's final measurement model)* |
| Manually dropped items | *(from paper — iterative refinement)* |
| Note | Burhān re-derives retention from the **designed** pool under PB-13 (protected; recommendations only). Deltas vs. the manual set are the item-level evidence for the supervisor's revision request. |

## 4. Divergence Classification

Every `REFERENCE_COMPARISON.md` row is resolved to exactly one, with rationale into provenance — **no side presumed correct**:

- **MATCH** — within tolerance; no action.
- **MANUAL_WEAKNESS** — engine exposes a prior-analysis error, gap, or inconsistency (e.g., an N-chain that doesn't reconcile, an un-run HTMT that fails, the H3a contradiction, a questionable retained item). Documented; feeds the supervisor's construct/item revision. **No engine change.**
- **ENGINE_OR_POLICY_CORRECTION** — a Burhān defect or a policy value producing a wrong/indefensible result. Fixed via a contract or researcher-governed change, then the run re-executes.
- **EXPECTED_METHOD_DIFFERENCE** — a legitimate, documented difference in approach the engine applies by policy (FIML vs. the manual treatment; HTMT added; Zhao–Lynch–Chen mediation classification). Recorded as method provenance, not a defect on either side.

Resolution completes when **unresolved = 0** and every non-MATCH row carries its classification and rationale.

## 5. Pass Criteria (M6)

- Stage-1A run reached a valid terminal state; all invariants passed; N-chain sums exactly.
- Both review gates passed; provenance complete; compliance checklist covers PB-01..PB-19.
- Re-run from the archived config reproduces identical outputs (NFR-101).
- `REFERENCE_COMPARISON.md` complete with **unresolved = 0**; every ENGINE_OR_POLICY_CORRECTION fixed and re-run; every MANUAL_WEAKNESS and EXPECTED_METHOD_DIFFERENCE documented.
- A short **Validation Findings** note summarizes: engine terminal state, the N-chain the engine derived, the measurement/fit/hypothesis comparison, and the item-retention deltas destined for the supervisor.

## 6. Sign-off

1. Claude Code executes §2, assembles `REFERENCE_COMPARISON.md` + Validation Findings; Codex verifies against ground truth (re-running as needed) and posts **GATE PASS** or **GATE FAIL** with exact deficiencies.
2. On GATE PASS, the researcher (with supervisor where applicable) reviews and records:
   `| M6 DBA validation | <date> | Researcher (+supervisor) | REFERENCE_COMPARISON.md unresolved=0 @ <commit> |`
3. That row unlocks TC-13. The validation-findings note and provenance become the AI-use-disclosure evidence and the researcher's revision dossier.

## 7. Boundaries

M6 changes no governed document and no engine behavior except through a §4 ENGINE_OR_POLICY_CORRECTION routed via normal change control. The DBA study's contract, results, and comparison live entirely under the engine-external studies root (FR-1402); nothing from it enters the engine repository. Hayat Tayyibah and all new-production studies remain blocked until M7 go-live.
