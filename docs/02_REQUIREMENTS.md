# Burhān — Requirements Specification (docs/02_REQUIREMENTS.md)

**Scope:** Phase 1 — CB-SEM v1 Core Release
**Status:** For review
**Traceability:** Every requirement carries a concept reference (§ = section of `01_CONCEPT.md`). Every acceptance test in `08_BUILD_SPEC.md` and `11_CERTIFICATION_PLAN.md` shall trace to at least one requirement ID.

**Conventions.** FR = functional requirement; NFR = non-functional requirement. Priorities: **P0** = required for Phase 1 acceptance; **P1** = required before go-live, may land late in Phase 1; **P2** = architectural allowance only (no functional delivery in Phase 1). "Shall" statements are binding and individually testable. Stage 1A / 1B markers indicate the internal delivery stage.

---

## 1. Functional Requirements

### FR-100 — Inputs & Ingestion (Stage 1A)

- **FR-101 (P0)** The system shall accept per study: a study document (PDF or DOCX), a raw survey export (XLSX or CSV), and optionally a data dictionary / instrument export. *(§12)*
- **FR-102 (P0)** The system shall accept a standing `decision_policy.yaml` and a standing Protected Decisions Registry configuration, with optional per-study overrides. *(§12)*
- **FR-103 (P0)** The system shall support survey-platform exports whose column headers are platform question codes with item identifiers embedded in secondary header rows (e.g., Qualtrics), and shall build a column→item crosswalk from the export itself. *(§8, §12)*
- **FR-104 (P0)** Ingestion shall fail hard, with a precise report, on structural mismatch between the data file and the study document (unresolvable columns, missing declared items). *(§10.3, §16)*

### FR-200 — Study Contract Extraction, Node A (Stage 1A)

- **FR-201 (P0)** Node A shall produce `study_config.yaml` containing: declared methodology; constructs including any higher-order structure; the **designed item-to-construct mapping** (the full instrument as designed); reverse-coded items; valid scale ranges; hypotheses and paths; mediators/moderators; control variables; demographic fields; instrument provenance. *(§8)*
- **FR-202 (P0)** The contract shall never encode a post-hoc retained item subset; item retention and deletion are pipeline outputs only. *(§8, §15)*
- **FR-203 (P0)** Node A output shall be validated against a strict schema (`05_schemas/study_config.schema.yaml`); any schema violation is a hard failure. *(§8)*
- **FR-204 (P0)** Where a data dictionary is provided, Node A extraction shall be cross-validated against it; unresolved conflicts are hard failures. *(§8, §12)*
- **FR-205 (P0)** Extraction ambiguity (unmappable item, unclear construct assignment, undeclared methodology) shall produce a hard failure with a precise report — never a guess or silent default. *(§5.4, §8)*
- **FR-206 (P0)** Node A shall never receive raw respondent-level data — documents and dictionary only. *(§5.2)*

### FR-300 — Review Gates, Node C (Stage 1A)

- **FR-301 (P0)** Review Gate 1 shall audit `study_config.yaml` against the source document (constructs, mappings, reverse-coded items, hypothesis paths, higher-order specification, declared methodology) before any pipeline stage consumes it. *(§8)*
- **FR-302 (P0)** Review Gate 2 shall audit the findings draft against the results store and `DECISION_LOG.md`, verifying claims are supported, appropriately hedged, and complete (all hypotheses reported, including unsupported ones). *(§8)*
- **FR-303 (P0)** Node C verdicts shall be approve or reject-with-exact-fixes; rejects trigger bounded author-node retries (bound set in policy); exhausting retries is a hard failure. *(§8)*
- **FR-304 (P0)** Node C shall run on a different model lineage than Node A, configured in the environment spec. *(§8, §11.6)*
- **FR-305 (P0)** Node C shall review artifacts only and shall have no capability to execute statistical computation or modify data. *(§8)*
- **FR-306 (P0)** Headless autonomy shall begin only after Gate 1 passes (the validated study contract); no operational human intervention shall be required from that point to run completion. *(§5.4, §7)*

### FR-400 — Power & Adequacy (Stage 1A)

- **FR-401 (P0)** The system shall compute a priori power at ingest: RMSEA-based test of close fit (MacCallum–Browne–Sugawara), N:q evaluation against playbook guidance, and Monte Carlo power simulation for the hypothesized model. *(§9.1)*
- **FR-402 (P0)** The system shall report achieved power at run end. *(§9.1)*
- **FR-403 (P0)** On inadequate sample for the approved method, the system shall complete what remains defensible, report the shortfall prominently, and where a paradigm-level remedy is indicated, emit a Method Advisory — never silently proceed and never switch paradigm. *(§9.1, §10.2)*

### FR-500 — Data Preparation (Stage 1A)

- **FR-501 (P0)** The preparation sequence (deduplication, attention-check filtering, straight-liner detection, reverse-coding, range enforcement, missing-data treatment, outlier handling) shall be implemented twice, independently, in R and in Python, with cell-level reconciliation; any unexplained difference halts the run with a discrepancy report. *(§11.1)*
- **FR-502 (P0)** Every incomplete response shall be profiled; cases at or above the policy inclusion threshold (default ≥90% of model items) shall be recovered into the analytical sample. *(§9.2)*
- **FR-503 (P0)** Missingness mechanism testing (Little's MCAR test plus a missingness pattern map) shall precede and gate the treatment choice. *(§9.2)*
- **FR-504 (P0)** FIML shall be the primary missing-data method; multiple imputation with Rubin's-rules pooling shall be the policy-selectable alternative. *(§9.2)*
- **FR-505 (P0)** Mean substitution as a default and any generation of synthetic cases shall be impossible by construction (no code path). *(§9.2)*
- **FR-506 (P0)** The system shall emit an exact N reconciliation chain — raw → duplicates → attention checks → straight-liners → recovered partials → outlier policy → final analytical N — whose counts sum exactly; failure to reconcile is a hard failure. *(§9.2, §11.2)*
- **FR-507 (P0)** Post-preparation invariants shall be asserted: all values within declared scale ranges; every reverse-coded item verified by correlation sign-flip; zero unmapped items; zero orphan columns; every hypothesized path resolvable; every construct at or above minimum item count; every declared higher-order structure fully specified. *(§11.2)*

### FR-600 — Assumptions & Estimator Determination (Stage 1A)

- **FR-601 (P0)** The system shall run univariate distribution checks, Mardia's multivariate normality, multicollinearity (VIF/tolerance), and multivariate outlier detection (Mahalanobis D² at the policy criterion). *(§9.3)*
- **FR-602 (P0)** Ordinal indicators shall never be treated as continuous by default; the playbook's conditions shall gate continuous treatment, with robust ML (MLR, Satorra–Bentler) where justified and WLSMV on polychoric correlations where policy conditions require. *(§9.4)*
- **FR-603 (P0)** The estimator determination and its rationale shall be written to `DECISION_LOG.md` on every run. *(§9.4, §10.1)*

### FR-700 — Measurement Model (Stage 1A)

- **FR-701 (P0)** The system shall estimate the CFA measurement model per the playbook, including second-order constructs, with the adopted higher-order approach (repeated-indicator or two-stage) declared per study and cited. *(§9.5)*
- **FR-702 (P0)** Reporting shall cover both levels of higher-order structures: first-order loadings, second-order loadings, and reliability/validity evidence at both levels. *(§9.5)*
- **FR-703 (P0)** The system shall compute α, CR, AVE, Fornell–Larcker, and HTMT (with the playbook ceiling), and evaluate loadings against the playbook target with significance tests, cross-loading inspection, and standardized residual covariance inspection. *(§9.6, §9.8)*
- **FR-704 (P0)** Common method bias shall be assessed with Harman's single-factor screen plus the common latent factor / marker variable technique as the substantive test. *(§9.8)*
- **FR-705 (P0)** Item deletion shall be **protected by default**: candidate deletions surface as recommendations unless deletion rules are explicitly pre-authorized in the decision policy. *(§9.7, §10.2)*
- **FR-706 (P0)** Where pre-authorized, deletion shall proceed one item at a time with full re-estimation after each; batch deletion shall not exist as a code path. *(§9.7)*
- **FR-707 (P0)** Each deletion shall require the dual trigger — a statistical signal and a content-validity check that the construct's conceptual domain remains intact — and shall respect a hard floor of three items per reflective construct. *(§9.7)*
- **FR-708 (P0)** Any deviation from a validated published instrument shall be prominently flagged; every deletion shall carry a complete before/after audit (reliability, validity, fit on both sides). *(§9.7)*
- **FR-709 (P0)** Respecification shall be limited to theory-consistent, within-construct error covariances, above the playbook MI threshold, applied cumulatively one at a time, under a hard maximum count, each logged with its index and justification rule. *(§9.6)*

### FR-800 — Structural Model & Effects (Stage 1A)

- **FR-801 (P0)** The system shall report global fit per the playbook band (χ² and normed χ², CFI, TLI, RMSEA with confidence interval, SRMR), standardized path estimates with bootstrapped confidence intervals, and R² per endogenous construct. *(§9.9)*
- **FR-802 (P0)** Mediation/moderation shall be estimated with 5,000-resample bootstrapping (policy-adjustable), reporting direct, indirect, and total effects with effect sizes and formal mediation classification (complementary / competitive / full / indirect-only). *(§9.9)*
- **FR-803 (P0)** The declared choice of full latent hierarchy versus validated latent scores in the structural model shall be recorded with rationale. *(§9.5)*

### FR-900 — Robustness & Independent Verification (Stage 1A)

- **FR-901 (P0)** The system shall run alternative model comparison per the playbook. *(§7 stage 8)*
- **FR-902 (P0)** The independent Python path shall verify preparation cell-by-cell, descriptives, derived metrics, model structure, and selected estimates **within the certified parity map**; verification scope shall be declared per run. *(§11.1)*
- **FR-903 (P0)** Areas outside validated parity shall be declared in `FLAGS.md`, never forced into agreement; divergence beyond hard thresholds halts the run. *(§11.1)*

### FR-1000 — Results Store & Narration, Node B (Stage 1B)

- **FR-1001 (P0)** All computed statistics shall be written to a structured results store in which every statistic carries a unique identifier (`05_schemas/results_store.schema.json`). *(§8)*
- **FR-1002 (P0)** Node B shall draft the findings chapter using statistic references only; numeric values shall be injected at render time from the results store. *(§8)*
- **FR-1003 (P0)** A post-generation checker shall fail the run if any number in the prose does not resolve to a results-store ID, or if any claim exceeds what the referenced statistics support (including prose/table consistency). *(§8)*
- **FR-1004 (P0)** The findings chapter shall follow the playbook's canonical chapter structure. *(§4.4)*
- **FR-1005 (P0)** Node B shall receive only the results store and approved contract/context artifacts — never raw respondent-level data. *(§5.2)*

### FR-1100 — Output Package (Stage 1B unless noted)

- **FR-1101 (P0, 1A)** Prepared analytical dataset + exact N reconciliation log. *(§12)*
- **FR-1102 (P0, 1A)** Power report (a priori and achieved); descriptives and assumption diagnostics including the estimator determination. *(§12)*
- **FR-1103 (P0, 1A)** Measurement results (both levels for higher-order), validity matrices, CMB assessment, item-deletion audit; structural results with respecification record; effects results; hypothesis testing matrix (H# → path → estimate → CI → verdict). *(§12)*
- **FR-1104 (P0)** Publication-ready tables (DOCX/XLSX, APA 7) and path diagram figures. *(§12)*
- **FR-1105 (P0)** SPSS/AMOS validation pack: SPSS-importable cleaned dataset, AMOS-ready covariance/correlation matrix, model diagram specification, SPSS-style descriptives, and a crosswalk table to expected SPSS/AMOS reporting fields. *(§12)*
- **FR-1106 (P0)** `METHOD_COMPLIANCE_CHECKLIST.md` recording every playbook step as completed, failed, or flagged. *(§4.5, §12)*
- **FR-1107 (P0)** `AI_USE_DISCLOSURE.md` stating what the system did and did not do, that all statistics were computed by deterministic code, that no data was fabricated, the LLM's bounded role, and researcher ownership of methodology. *(§12)*
- **FR-1108 (P0)** `SUPERVISOR_REVIEW_PACK.docx` with model summary, sample and N reconciliation, measurement quality, fit, hypothesis matrix, decisions requiring approval, flags and limitations. *(§12)*
- **FR-1109 (P0, 1A)** `DECISION_LOG.md`, `FLAGS.md`, `METHOD_ADVISORY.md` (when applicable), the provenance archive, and a reproducibility manifest (seed, lockfiles, config hashes, playbook version). *(§10.4, §12)*

### FR-1200 — Decision Governance (Stage 1A)

- **FR-1201 (P0)** Every operational judgment shall resolve through `decision_policy.yaml`; each decision shall log the rule fired. *(§10.1)*
- **FR-1202 (P0)** The Protected Decisions Registry shall be enforced architecturally: no code path shall execute paradigm change, hypothesis change, construct change, validated-instrument deviation, or (by default) item deletion. *(§10.2)*
- **FR-1203 (P0)** When evidence challenges the approved approach, the system shall emit `METHOD_ADVISORY.md` (diagnostics, recommendation, citations, impact) and continue only to the boundary of what remains defensible. *(§10.2)*
- **FR-1204 (P0)** Hard failure shall be reserved for integrity violations (unusable response quality, data–document mismatch, invariant violation, verification mismatch, exhausted gate); all else resolves by policy, logged and flagged. *(§10.3)*

### FR-1300 — Playbook Engine (Stage 1A)

- **FR-1301 (P0)** Playbooks shall be versioned modules validated against `PLAYBOOK_SCHEMA`; the playbook version shall be recorded in every run manifest. *(§4.1)*
- **FR-1302 (P0)** No playbook, no run: an undeclared or unsupported methodology shall produce a clean refusal with a report. *(§3, §4.3)*
- **FR-1303 (P0)** Method binding shall be a protected decision; the engine shall load exactly the declared playbook. *(§4.3)*
- **FR-1304 (P2)** The playbook interface shall accommodate future PLS-SEM and assisted-qualitative playbooks without engine modification (interface only; no Phase 1 functionality). *(§6, §17)*

### FR-1400 — Study Management & CLI (Stage 1A)

- **FR-1401 (P0)** One CLI command shall execute a full run given a study folder path; no interactive input shall be required after Gate 1. *(§10.3)*
- **FR-1402 (P0)** The engine and studies shall be structurally separated per the repository contract; engine code shall contain zero references to any specific study. *(§13)*
- **FR-1403 (P0)** Each run shall be archived under `studies/<study>/runs/<timestamp>/` with everything required for bit-identical re-execution. *(§13, NFR-101)*

### FR-1500 — Certification & Validation Harnesses (Stage 1A harness, run pre-go-live)

- **FR-1501 (P0)** A golden-dataset harness shall verify 100% detection of all defined planted defects (duplicates, straight-liners, out-of-range, un-reversed items, engineered missingness, known outliers) and zero unexplained dual-path differences. *(§11.3, §14)*
- **FR-1502 (P0)** A benchmark replication harness shall reproduce published worked examples within tolerance across measurement (including higher-order), structural, and mediation stages, and shall establish the documented cross-engine parity map. *(§11.4)*
- **FR-1503 (P0)** The DBA validation run shall consume the designed-instrument contract and produce a **reference comparison report** against the prior manual analysis — cleaning decisions, analytical N, item-retention deltas, measurement and structural results, hypothesis verdicts — with divergences investigated and classified (manual weakness vs engine/policy correction), no side presumed correct. *(§15)*
- **FR-1504 (P0)** Certification and validation suites shall remain in the repository as permanent regression gates. *(§5.8, §11)*

---

## 2. Non-Functional Requirements

### NFR-100 — Determinism & Reproducibility

- **NFR-101 (P0)** A re-run from an archived run manifest shall reproduce byte-identical outputs (fixed seeds; pinned R and Python environments; hashed config, policy, and playbook). *(§5.9, §14)*
- **NFR-102 (P0)** Any change to policy, playbook, or contract shall change the recorded hashes; silent drift shall be impossible. *(§4.1, §5.9)*

### NFR-200 — Failure Semantics

- **NFR-201 (P0)** All failures shall be loud, immediate at the failing stage, and accompanied by a machine-readable and human-readable report; there shall be no code path that silently alters data, skips a check, or abbreviates a stage. *(§5.7)*
- **NFR-202 (P0)** Partial results present at a hard failure shall be preserved in the run archive, clearly marked non-final. *(§10.3)*

### NFR-300 — Auditability

- **NFR-301 (P0)** Every decision, rule fired, row dropped, item deleted, and modification applied shall append a structured provenance entry (trigger, rule reference, effect) sufficient to reconstruct the run narrative without the researcher present. *(§11.7)*
- **NFR-302 (P0)** `DECISION_LOG.md` and `FLAGS.md` shall be readable end-to-end by the researcher in 30–45 minutes for a typical study. *(§10.4)*

### NFR-400 — Data Locality & LLM Boundary

- **NFR-401 (P0)** All statistical computation and data manipulation shall execute locally on the researcher's workstation; no raw respondent-level data shall leave the machine or be included in any LLM prompt, regardless of provider configuration. *(§3, §5.2)*
- **NFR-402 (P0)** LLM nodes shall be schema-bound: inputs and outputs validated; no numeric result originating from an LLM shall enter the results store. *(§5.1–5.2, §8)*

### NFR-500 — Performance & Operation

- **NFR-501 (P0)** A full Phase 1 run on a typical survey study (N ≤ 2,000 raw; ≤ 150 items; 5,000 bootstrap resamples) shall complete unattended within an overnight window on the reference workstation. *(§3)*
- **NFR-502 (P1)** Stage-level progress and timing shall be logged for run diagnostics. *(§13 runbook support)*

### NFR-600 — Testability & Coverage

- **NFR-601 (P0)** Every FR shall be covered by at least one automated test; certification suites run green before the first validation run and in regression thereafter. *(§14)*
- **NFR-602 (P0)** Statistical modules shall carry unit tests against known-answer fixtures independent of the certification suites. *(§11.4)*

### NFR-700 — Extensibility

- **NFR-701 (P0)** Phase 2/3 additions shall require new playbooks and policy entries only — no engine-core modification and no change to Phase 1 acceptance behavior. *(§6, §17)*

### NFR-800 — Operability

- **NFR-801 (P0)** New-study onboarding (folder, inputs, contract, first run) shall be executable from the runbook alone, without reading engine source. *(§13)*
- **NFR-802 (P1)** All operator-facing messages (halts, flags, advisories) shall state the condition, the governing rule, and the next action. *(§10, §13)*

---

## 3. Explicit Exclusions (Phase 1)

Web frontend/backend or multi-user access; survey design or data collection; autonomous qualitative analysis; PLS-SEM functionality beyond the playbook interface (FR-1304); engine-level references to any specific study. *(§3, §6)*

---

## 4. Requirement-to-Concept Trace Summary

Inputs FR-100→§12 · Contract FR-200→§8,§15 · Gates FR-300→§8,§11.6 · Power FR-400→§9.1 · Preparation FR-500→§9.2,§11.1–11.2 · Assumptions FR-600→§9.3–9.4 · Measurement FR-700→§9.5–9.8 · Structural FR-800→§9.9 · Robustness FR-900→§11.1 · Narration FR-1000→§8,§4.4 · Outputs FR-1100→§12 · Governance FR-1200→§10 · Playbooks FR-1300→§4 · CLI/Studies FR-1400→§13 · Certification FR-1500→§11,§14,§15 · NFRs→§3,§5,§10–§14.
