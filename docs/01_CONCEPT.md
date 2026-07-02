# Burhān (برهان)
## Autonomous Research Analysis Engine — Concept Document

**Owner:** Salim Al Barami
**Status:** For approval
**Classification:** Personal research infrastructure (with future productization path)

---

## 1. Executive Summary

Burhān is a locally deployed research analysis engine that takes a study document (research model, framework, hypotheses) and raw survey data, and produces a complete, defensible academic analysis: prepared data, method-appropriate results, hypothesis outcomes, publication-ready tables and figures, a drafted findings chapter, and a full decision provenance log.

Its governing doctrine: **each supported methodology is implemented through a citation-backed, researcher-approved analytical playbook — supervisor-approved where applicable** — that formalizes the accepted methodological sequence, decision points, thresholds, and reporting requirements. Burhān executes the approved playbook consistently and transparently — never an improvised approximation of it. Where the field holds legitimate scholarly variation (thresholds, estimators, fit-index interpretation), the playbook records the position the method owner has adopted, with its citations, and applies it uniformly.

Burhān runs headlessly **after the study contract has been validated**: once `study_config.yaml` passes schema validation and reviewer audit, all operational analytical stages proceed without human intervention, resolved by a pre-approved decision policy. A defined class of **protected decisions** — paradigm, hypotheses, constructs, validated instruments, and item deletion — remains architecturally reserved for explicit human approval.

It is a **system, not a prompt workflow**: deterministic, tested code is the runtime. Language models are confined to three narrow, schema-validated roles — understanding the study document, drafting the findings narrative from computed results, and internally auditing artifacts. **The LLM never touches raw respondent-level data and never performs statistical computation**; it reads only validated study documents, structured result summaries, and generated artifacts.

Delivery is phased and validation-first. **Phase 1 is the CB-SEM v1 Core Release** — complete, end-to-end, fully functional on its own, dependent on nothing outside itself — and its **first run is a validation run against the researcher's already-completed DBA study**, used as a documented methodological reference case, before the engine is applied to any new research. Later phases extend the playbook library; nothing in Phase 1 waits on them.

The name is deliberate: *burhān* is demonstrative proof — the highest evidentiary standard in classical logic. A research engine should be held to nothing less.

---

## 2. Problem Statement

Rigorous academic research (DBA theses, journal submissions, applied studies) currently requires weeks of manual work across SPSS, AMOS, and manual drafting: cleaning data, validating measurement, estimating models, extracting results into tables, and writing findings. This work is:

- **Slow** — the same mechanical sequence is rebuilt by hand for every study.
- **Error-prone** — data preparation mistakes are silent, compound downstream, and are rarely audited.
- **Non-reusable** — nothing from one study's analysis transfers to the next.
- **Inconsistently rigorous** — whether the full accepted protocol (power analysis, assumption testing, validity assessment, bias checks) is actually followed depends on researcher discipline under deadline pressure.
- **Poorly documented** — analytical decisions live in the researcher's head, exactly where a viva panel or journal reviewer will probe.

The cost of not solving it: every future study pays the full manual price again, and the weakest links — data cleaning and process discipline — remain the least verified stages of the research process.

---

## 3. What Burhān Is — and Is Not

**Burhān is:**

- A reusable analysis engine: one system, unlimited studies. A new study is a new folder, never new code.
- **Playbook-faithful:** it executes the citation-backed, researcher-approved playbook for the study's declared method. No playbook, no run — the system refuses cleanly rather than improvises.
- Autonomous within a validated mandate: after the study contract passes validation and audit, a run completes headlessly (overnight-capable) with no human intervention on operational decisions.
- **Governed at the boundary:** decisions that belong to the method owner — paradigm, hypotheses, constructs, validated instruments, item deletion — are architecturally impossible for the system to take on its own.
- Verifiable by construction: an authoritative estimation engine with independent verification, hard invariants, an internal reviewer agent, and certification against defect-seeded datasets, published benchmarks, and the researcher's own completed study before it analyzes anything new.
- Locally sovereign: runs entirely on the researcher's workstation. No cloud dependency for data processing.
- Audit-native: every decision, dropped row, deleted item, and changed value is logged in a provenance chain suitable for viva defense, journal review, and AI-use disclosure — with a formal disclosure document produced as a standard output.

**Burhān is not:**

- A platform. No web frontend, no backend services, no multi-user access in Phase 1. (Single-researcher tool; UI plumbing would consume the build effort while adding no analytical value. Productization is a documented future path.)
- A data collection tool. Survey design and administration are out of scope.
- An SPSS/AMOS replacement UI. It replaces the *workflow*, not the software category — and it produces an SPSS/AMOS validation pack precisely so that conventional academic verification remains straightforward.
- A methodologist of record. It executes the approved methodology consistently and transparently; it does not choose or change the methodology. Ownership of method remains with the researcher — and with the supervisor where one exists — by design and for academic integrity.
- A qualitative researcher. Future qualitative playbooks are **assisted**, not autonomous: they support coding discipline, audit trails, and traceability while preserving human ownership of interpretive work.
- A data fabricator. It recovers and correctly treats *real* partial responses; it never generates synthetic respondents or invents values. That line is data fabrication, and the provenance log is standing proof it was never crossed.

---

## 4. The Playbook Doctrine

The methodological literature defines, for each established method, accepted protocols with a defensible logical order, named decision points, published thresholds, and reporting standards — alongside areas of legitimate scholarly variation. Burhān resolves this honestly: **a playbook is the method owner's adopted position within the accepted literature, codified as an executable specification** — researcher-approved, and supervisor-approved where applicable.

**4.1 The Methods Playbook library.** Each supported methodology is encoded as a versioned playbook module (e.g., `CB_SEM_PLAYBOOK_v1.0.yaml`): the analytical stage sequence, the decision points with their literature-defined criteria and citations, the quality thresholds adopted, the required diagnostics, and the reporting standard (APA 7 and the APA Journal Article Reporting Standards — JARS — plus thesis chapter conventions). Playbooks are compiled into the deterministic pipeline; they are the curriculum, and the engine is the executor. The playbook version used is recorded in every run's reproducibility manifest, so evolving thresholds never silently change past results.

**4.2 Illustrative playbook content:**

- **CB-SEM playbook (Phase 1; Anderson–Gerbing two-step tradition; Hair et al., Kline, Byrne):** data screening → descriptives and assumption testing → sampling adequacy and a priori power → measurement model (CFA: reliability, convergent and discriminant validity, including higher-order structures) → common method bias assessment → structural model (fit, paths, explained variance) → mediation/moderation via bootstrapping → robustness and alternative models → APA/JARS reporting.
- **PLS-SEM playbook (Phase 2; Hair et al. primer tradition):** measurement model assessment (reflective: loadings, composite reliability, AVE, HTMT; formative: indicator collinearity, weight significance and relevance) → structural model assessment (collinearity, bootstrapped path significance, R², f², Q², predictive relevance) → reporting per PLS-SEM standards.
- **Thematic analysis playbook (Phase 3, assisted; Braun & Clarke six-phase):** the system supports coding discipline, code–quote traceability, theme audit trails, intercoder reliability computation, and report drafting — while interpretive theme construction remains researcher-owned, governed by qualitative trustworthiness criteria (credibility, transferability, dependability, confirmability).

**4.3 Method binding.** The study document declares the methodology; the extraction node identifies it; the engine loads exactly that playbook. The declared method is a **protected decision** (Section 10): the system may recommend reconsideration with evidence, but only a human may change it.

**4.4 Narration follows the playbook too.** The findings chapter is drafted in the playbook's chapter structure (for CB-SEM: sample profile → data screening summary → measurement validation → structural results → hypothesis summary), so the output drops into a thesis or manuscript without structural rework.

**4.5 Compliance is evidenced, not assumed.** Every run emits a Method Compliance Checklist recording each playbook step as completed, failed, or flagged — distinct from the decision log — proving the approved sequence was followed in full.

---

## 5. Design Principles

1. **Code is the runtime; the LLM is a component.** All data manipulation and statistics run in deterministic, version-pinned R and Python code. LLM inference appears only where language understanding, language production, or artifact audit is the task itself.

2. **The LLM never touches raw respondent-level data and never performs statistical computation.** It reads validated study documents, structured result summaries, and generated artifacts; it writes configuration and narrative. It never performs an operation on a dataset and never produces a numeric result.

3. **Playbook fidelity over convenience.** When the approved playbook and expedience conflict, the playbook wins. Stages are never skipped, reordered, or abbreviated; if a stage cannot be completed, the run fails loudly with a precise report, and the compliance checklist records it.

4. **Autonomy begins at the validated contract.** The high-risk stage is understanding the study; it is guarded by schema validation and reviewer audit, and ambiguity there is a hard failure, never a guess. Past that boundary, the system never pauses for operational questions — every operational judgment is resolved by `decision_policy.yaml`, a researcher-authored, version-controlled rulebook. Disagreement with an outcome is handled by editing the policy and re-running.

5. **Human sovereignty over theory.** Decisions with theoretical or supervisory standing are registered as protected and are architecturally outside the system's authority.

6. **Sanad applied to analysis.** Trust comes from independent chains: an authoritative estimation engine verified by an independent implementation wherever equivalence is validated, and artifacts audited by a reviewer node of a different model lineage than their author. Where independent verification is not technically supportable, the gap is declared and flagged — never papered over.

7. **Fail loudly, never silently.** Hard invariants are asserted at every stage. There is no code path in which data is silently altered, a check silently skipped, or a stage silently abbreviated.

8. **Trust is earned mechanically, and proven on a known case.** Before first use on new research, the engine must pass certification — 100% detection of all defined planted defects in the certification suite, and replication of published worked examples within tolerance — and then independently re-analyze the researcher's own completed study under its documented methodology. The suites remain as permanent regression gates.

9. **Reproducibility is a feature.** Fixed seeds, locked package versions, hashed configs, versioned playbooks, archived runs. Any output can be regenerated bit-for-bit from its run archive.

---

## 6. Phased Delivery

**Phase 1 — CB-SEM v1 Core Release (the build commitment).** The CB-SEM playbook end-to-end, complete and fully functional on its own, with **no functional dependency on any later phase**. To keep the build realistic and prove the engine before the reporting layer, Phase 1 is delivered in two internal stages — and Phase 1 is complete only when both are:

- **Stage 1A — Trusted Analytical Core:** study contract extraction and validation; power and adequacy analysis; data preparation with partial-response recovery and exact N reconciliation; descriptives and assumption diagnostics (including ordinal-indicator governance); CFA measurement validation including higher-order constructs; common method bias assessment; structural estimation; bootstrapped mediation/moderation; robustness; decision log, flags, provenance, and reproducibility manifest.
- **Stage 1B — Academic Output Layer:** publication-ready tables and figures; drafted findings chapter; SPSS/AMOS validation pack; Method Compliance Checklist; AI-use disclosure; supervisor review pack.

Stage 1A must be trusted — certified and validated against the researcher's completed DBA study (Section 15) — before Stage 1B outputs are relied upon. The playbook interface is the only forward-looking element in Phase 1, and it is architecture, not deferred function.

**Phase 2 — Quantitative extensions (optional, later).** PLS-SEM playbook (`seminr`), multi-group analysis and measurement invariance, additional quantitative designs (regression families, ANOVA/MANOVA, longitudinal SEM). Each arrives as a versioned playbook behind the same governance, verification, and provenance framework.

**Phase 3 — Assisted qualitative playbooks (optional, later).** Thematic analysis and related methods as **researcher-led, system-assisted** workflows: the system provides coding discipline, audit trails, traceability, reliability computation, and drafting support; the researcher owns interpretation. No autonomous qualitative analysis is promised, in this phase or any other.

---

## 7. System Architecture (Conceptual)

A typed, stage-gated pipeline (LangGraph or equivalent DAG). Each stage consumes validated artifacts from the previous stage and emits validated artifacts plus provenance entries.

```
INPUTS
  study document (PDF/DOCX)        ─┐
  raw data (XLSX/CSV)               ─┤
  data dictionary (recommended)     ─┤
                                     ▼
[1] INGEST & EXTRACT        LLM Node A: document → study_config.yaml
                            (methodology identified; schema-validated;
                            cross-checked against data dictionary if provided)
                              ▼
      ◆ REVIEW GATE 1       LLM Node C audits study_config against the
                            source document (approve / reject with fixes)
                    ── validated study contract: autonomy begins here ──
                              ▼
[2] POWER & ADEQUACY        a priori power analysis; sampling adequacy;
                            N:q evaluation
                              ▼
[3] PREPARE                 dual-implementation R + Python preparation;
                            partial-response recovery; invariants +
                            N reconciliation chain
                              ▼
[4] DESCRIBE & TEST         descriptives; univariate & multivariate
                            assumption diagnostics; missingness mechanism;
                            ordinal-indicator estimator determination
                              ▼
[5] MEASUREMENT MODEL       CFA per playbook, incl. higher-order structures:
                            reliability, convergent & discriminant validity;
                            item-deletion governance; CMB assessment
                              ▼
[6] STRUCTURAL MODEL        fit indices; path estimates; R²;
                            policy-bounded respecification
                              ▼
[7] EFFECTS                 bootstrapped mediation / moderation;
                            effect sizes
                              ▼
[8] ROBUSTNESS              alternative model comparison; independent
                            estimate verification; achieved power
                              ▼
[9] REPORT                  LLM Node B: results store → findings draft
                            in the playbook's chapter structure
                            (statistic references, never free-text numbers)
                              ▼
      ◆ REVIEW GATE 2       LLM Node C audits the draft against the results
                            store and DECISION_LOG (approve / reject)
                              ▼
OUTPUT PACKAGE              tables, figures, hypothesis matrix, findings
                            chapter, SPSS/AMOS validation pack, compliance
                            checklist, disclosure, supervisor pack,
                            DECISION_LOG, FLAGS, METHOD_ADVISORY (if any),
                            provenance archive
```

**Engines:** R (`lavaan`, `semTools`, `simsem`) is the **authoritative estimation engine** for CB-SEM. Python (`pandas`, `semopy`) independently verifies data preparation, descriptive statistics, derived metrics, model structure, and selected estimates **where package equivalence has been validated**; any area where parity is not technically supportable is explicitly declared in FLAGS rather than forced. Both environments pinned and locked.

---

## 8. The Three LLM Nodes

**Node A — Study Understanding.** Input: the study document (plus the data dictionary where provided). Output: `study_config.yaml` — declared methodology, constructs (including higher-order structure where specified), the **designed item-to-construct mapping** — the full instrument as designed, never any post-hoc retained subset, because item retention and deletion are pipeline outputs under Section 9.7 governance, not inputs — reverse-coded items, valid scale ranges, hypotheses and paths, mediators/moderators, control variables, demographic fields, and instrument provenance (validated scales and their sources). Output is validated against a strict schema and, where a data dictionary exists, cross-checked against it; ambiguity is a hard failure, never a guess. This file is the study contract driving the deterministic pipeline.

**Node B — Findings Narration.** Input: the computed results store — structured JSON in which **every statistic carries a unique identifier**. Output: a drafted findings chapter in academic register, structured per the playbook's chapter order. The draft is composed with **statistic references, not free-text numbers**; values are injected programmatically at render time, and a post-generation checker fails the run if any number in the prose does not resolve to a results-store ID, or if any claim exceeds what the referenced statistics support.

**Node C — Reviewer (the Muḥāsaba node).** An internal audit agent replicating the researcher's external review protocol *inside* the system, running on a **different model lineage** than Node A (lineage independence per the Sanad principle). Two checkpoints:

- **Review Gate 1 (post-extraction):** audits `study_config.yaml` against the source document — every construct, item mapping, reverse-coded item, hypothesis path, higher-order specification, and the declared methodology — before the pipeline consumes it. Passing this gate is what converts the extraction into a **validated study contract**, the boundary at which autonomy begins.
- **Review Gate 2 (post-report):** audits the findings draft against the results store; checks DECISION_LOG coherence; verifies interpretive claims are supported, hedged appropriately, and complete (no unreported failed hypotheses).

Verdicts are approve / reject-with-exact-fixes; rejects trigger bounded retries (author node corrects, reviewer re-audits), then hard failure. Node C reviews **artifacts only — it never re-computes statistics**; numeric truth belongs exclusively to the deterministic code.

Everything between the gates is pure code.

---

## 9. Methodologically Governed Statistical Execution

The engine's statistical competence is not claimed of a language model; it is **engineered into the playbooks** as codified, citation-backed protocols (Hair et al.; Kline; Byrne; Podsakoff et al.; Henseler et al.; Fornell & Larcker; Little; MacCallum, Browne & Sugawara). The capabilities below are Phase 1 commitments for the CB-SEM playbook.

**9.1 Power analysis — before, not after.**
- A priori at ingest: RMSEA-based test of close fit (MacCallum–Browne–Sugawara), N:q ratio evaluation against playbook guidance, and Monte Carlo power simulation (`simsem`) for the hypothesized model.
- Achieved-power reporting at the end of every run.
- If the analytical sample is inadequate for the approved method, the system completes what is defensible, reports the power shortfall prominently, and — where the evidence suggests a paradigm-level remedy — issues a Method Advisory (Section 10). It never silently proceeds underpowered, and never switches paradigm on its own.

**9.2 Missing data & partial-response intelligence.**
- Every incomplete response is profiled, not discarded. Cases meeting the policy inclusion threshold (e.g., ≥90% of model items answered) are recovered into the analytical sample.
- Missingness mechanism testing: Little's MCAR test plus a missingness pattern map determine what treatment is defensible.
- Primary recovery method: **FIML** — full-information maximum likelihood, the SEM-native standard that uses every answered item from every retained case without fabricating a single value. Multiple imputation with pooled estimates (Rubin's rules) is the policy-selectable alternative.
- Prohibited by construction: mean substitution as a default, and any generation of synthetic cases. Recovery means correctly using real respondents' real answers — nothing else.
- The N reconciliation chain records the arithmetic exactly: raw → after duplicates → after attention checks → after straight-liners → recovered partials in → after outlier policy → final analytical N. Counts must sum exactly.

**9.3 Multivariate diagnostics.** Mardia's multivariate normality (skewness/kurtosis), univariate distribution checks, multicollinearity (VIF, tolerance), and multivariate outliers (Mahalanobis D² at the policy-set criterion). Consequences are routed through policy — e.g., multivariate non-normality triggers the robust estimator adjustment (ML → MLR with Satorra–Bentler corrections), a *within-method* adjustment and therefore autonomous.

**9.4 Ordinal indicator governance.** Likert-type items are never assumed continuous by default. The playbook encodes the conditions under which ordinal indicators may be treated as continuous (e.g., sufficient response categories and distributional behavior within the adopted thresholds); robust ML (MLR) is applied where justified; and where policy conditions require it (few categories, strong non-normality), estimation proceeds via **WLSMV on polychoric correlations**. The estimator determination and its rationale are logged in the decision log for every run — because ML on ordinal data is precisely the kind of choice a reviewer will challenge, and the answer must already be on file.

**9.5 Higher-order construct support.** Phase 1 explicitly supports second-order constructs, not only first-order reflective measurement:
- Higher-order CFA specification and reporting: first-order loadings, second-order loadings, and reliability/validity evidence at both levels.
- The playbook's adopted approach — repeated-indicator or two-stage — declared per study in the contract, with citations.
- An explicit, recorded choice of whether the structural model carries the full latent hierarchy or validated latent scores, with the rationale logged.
Multi-pillar frameworks modeled as second-order constructs are a first-class case, not an edge case.

**9.6 Measurement quality & covariance discipline.** Standardized loadings evaluated against the playbook target (≥ 0.708, the AVE-logic threshold) with significance testing; cross-loading inspection; standardized residual covariance matrix inspection; modification indices consulted only within the respecification limits (theory-consistent, within-construct error covariances only, hard maximum count, every modification logged with its index and justification rule).

**9.7 Item deletion — protected by default.** Item removal to improve reliability or validity is the classic p-hacking trapdoor, so it is governed at the highest level:
- **Default: protected.** Autonomous deletion is permitted only where the researcher has pre-authorized the rule in the decision policy — otherwise candidate deletions surface as recommendations requiring human approval.
- Where pre-authorized: one item at a time, with **full model re-estimation after each** removal — never batch deletion.
- **Dual trigger required:** a statistical signal (low loading, reliability improvement, discriminant violation) *and* a content-validity check confirming the construct's conceptual domain remains theoretically intact.
- Hard floor of three items per reflective construct.
- Any deviation from a validated published instrument is prominently flagged in FLAGS and the provenance log.
- Complete before/after audit: reliability, validity, and fit statistics on both sides of every deletion.

**9.8 Construct validity protocol.** Convergent validity (AVE ≥ 0.50, CR ≥ 0.70, loading significance), discriminant validity by both Fornell–Larcker and HTMT (with the playbook ceiling), and common method bias assessment (Harman's single-factor as screen; common latent factor / marker variable technique as the substantive test).

**9.9 Structural evaluation.** Global fit per the playbook band (χ² and normed χ², CFI, TLI, RMSEA with confidence interval, SRMR), standardized path estimates with bootstrapped confidence intervals, R² per endogenous construct, effect sizes, and formal mediation typology (direct/indirect/total effects; complementary vs. competitive vs. full mediation classification) from 5,000-resample bootstrapping.

---

## 10. Decision Governance

Every decision in a run belongs to exactly one of two registered classes.

**10.1 Policy-resolvable (autonomous after the validated contract).** Operational judgments encoded in `decision_policy.yaml`: cleaning thresholds, inclusion rules, imputation method, outlier treatment, estimator **robustness adjustments within the approved method** (e.g., ML → MLR when normality fails; WLSMV when ordinal conditions require it), bootstrap parameters, respecification within caps, reporting formats. The system decides per rule, logs the rule fired, and proceeds.

**10.2 Protected (human-only).** Decisions with theoretical or supervisory standing, registered in the **Protected Decisions Registry**:
- Analytical paradigm change — CB-SEM ↔ PLS-SEM, quantitative ↔ qualitative, or any change to the approved method.
- Hypothesis addition, removal, or modification.
- Construct redefinition, merging, or splitting — including changes to a declared higher-order structure.
- Deviation from a validated instrument.
- **Item deletion (protected by default; delegable only by explicit pre-authorization in the decision policy).**

The system **cannot execute** a protected decision. If accumulated evidence genuinely challenges the approved approach, it runs to the boundary of what remains defensible and issues a **Method Advisory**: the diagnostics, the recommendation, the literature citations, and the impact assessment — then stops there. The researcher decides (with the supervisor where applicable), the decision is recorded with its rationale, and the re-run proceeds under the amended mandate. The advisory and the human decision both enter the provenance chain — precisely the documentation a viva panel wants to see.

**10.3 Run behavior.** One CLI command starts a run. Hard failure is reserved for integrity violations: unusable response quality, structural mismatch between data and study document, invariant violation, verification mismatch, or an exhausted review gate. Everything else is resolved by policy, logged, and flagged — never blocked on.

**10.4 Review at the end, asynchronously.** The output package includes `DECISION_LOG.md` (every policy decision taken, with rules cited), `FLAGS.md` (everything warranting researcher attention, ranked), and `METHOD_ADVISORY.md` when applicable. Expected researcher review: 30–45 minutes per study, whenever convenient. An optional 5-minute glance at `study_config.yaml` before a run remains available as a cheap correctness lever but is not required.

---

## 11. Trust & Verification Framework

**11.1 Authoritative engine plus independent verification.** R/lavaan is the authoritative estimation engine for CB-SEM. The independent Python path verifies data preparation cell-by-cell, descriptive statistics, derived metrics, model structure, and selected estimates where package equivalence has been validated during certification. Verification scope is declared per run; any area outside validated parity is explicitly flagged rather than forced into false agreement. Preparation-stage disagreement halts the run with a discrepancy report.

**11.2 Hard invariants (asserted, not assumed).**
- Every value within its declared scale range after preparation.
- Every reverse-coded item verified by correlation sign-flip against its construct.
- Zero unmapped items; zero orphan columns.
- N reconciliation chain sums exactly (Section 9.2).
- Every hypothesized path resolvable from the config; every construct at or above its minimum item count; every declared higher-order structure fully specified.

**11.3 Golden-dataset certification.** Synthetic surveys with planted defects — duplicates, straight-liners, out-of-range values, un-reversed items, engineered missingness, known outliers — with **100% detection of all defined planted defects in the certification suite** required before first live use.

**11.4 Benchmark replication certification.** The engine must reproduce published worked examples from the methodological literature — same inputs, same outputs within tolerance, across measurement models (including higher-order), structural models, and mediation analyses. Certification also establishes the validated cross-engine parity map used in 11.1. This is the mechanical demonstration that the system executes the approved protocols correctly: it produces the literature's answers on the literature's problems.

**11.5 Known-case validation.** Beyond synthetic and published benchmarks, the engine's first full run is against the researcher's own completed, manually analyzed study (Section 15) — the strongest available real-world reference case: its approved methodology, model, structure, and thresholds are fully documented, while its prior manual results serve as a comparison point rather than presumed truth.

**11.6 Lineage-independent review.** Node C runs on a different model lineage than Node A, so extraction and audit never share a failure mode.

**11.7 Provenance chain.** Every decision, rule fired, row dropped, item deleted, and modification applied — with trigger, rule reference, and effect — is appended to a structured provenance log: the *sanad* of the analysis. It is simultaneously the debugging trail, the viva defense file, and the evidentiary basis of the AI-use disclosure.

---

## 12. Inputs & Outputs

**Inputs (per study):**
1. Study document — research model, theoretical framework, constructs, hypotheses, declared methodology (PDF or DOCX).
2. Raw data — survey export (Excel/CSV).
3. **Recommended:** data dictionary / survey instrument export — item labels, scale ranges, skip logic, reverse-coded items, construct mapping. When provided, Node A extraction is cross-validated against it, materially reducing contract risk.
4. (Standing) `decision_policy.yaml` — shared across studies unless overridden per study.
5. (Standing) Protected Decisions Registry configuration.

**Output package (per run):**
- Prepared analytical dataset + exact N reconciliation log.
- Power analysis report (a priori and achieved).
- Descriptives, full assumption diagnostics, and the estimator determination with rationale.
- Measurement model results: loadings (both levels for higher-order structures), α, CR, AVE, Fornell–Larcker, HTMT, CMB assessment, item-deletion audit (if any).
- Structural model results: fit indices, standardized paths with bootstrapped CIs, R², respecification record.
- Mediation/moderation results with effect sizes and mediation classification.
- Hypothesis testing matrix (H# → path → estimate → CI → supported / not supported).
- Publication-ready tables (DOCX/XLSX, APA 7) and path diagram figures.
- Drafted findings chapter in the playbook's structure, all numbers resolved from results-store IDs.
- **SPSS/AMOS validation pack:** cleaned dataset in SPSS-importable form, AMOS-ready covariance/correlation matrix, model diagram specification, SPSS-style descriptives, and a crosswalk table mapping Burhān outputs to the expected SPSS/AMOS reporting fields — so conventional supervisory verification is straightforward.
- **`METHOD_COMPLIANCE_CHECKLIST.md`:** every playbook step recorded as completed, failed, or flagged — evidence the approved sequence was followed in full.
- **`AI_USE_DISCLOSURE.md`:** a formal statement of what the system did and did not do — that all statistics were computed by deterministic code, that no data was fabricated, what the LLM's role was limited to, and that the researcher retained methodological ownership. Written to satisfy institutional AI-use disclosure requirements.
- **`SUPERVISOR_REVIEW_PACK.docx`:** study model summary, final sample and N reconciliation, measurement quality summary, fit indices, hypothesis matrix, decisions requiring approval, flags and limitations — a self-contained governance document for supervisory review.
- `DECISION_LOG.md`, `FLAGS.md`, `METHOD_ADVISORY.md` (when applicable), provenance archive, and a reproducibility manifest (seed, package lockfile, config hashes, playbook version).

---

## 13. Reusability Model

```
burhan/                      ← the engine (one repo, versioned)
  playbooks/                 ← versioned method playbooks
    CB_SEM_PLAYBOOK_v1.0.yaml        (Phase 1)
    PLS_SEM_PLAYBOOK_v*.yaml         (Phase 2)
    THEMATIC_ASSISTED_v*.yaml        (Phase 3, assisted)
studies/
  dba-validation-study/      ← first: the completed DBA study (benchmark)
    inputs/  config/  runs/  outputs/
  hayat-tayyibah-2026/       ← first new-production study, after validation
    inputs/  config/  runs/  outputs/
  <next-study>/
```

The engine is never edited for a study. A new study is: create folder, drop inputs, run. **The first validation study is the researcher's completed DBA study, selected because its documented methodology and prior manual analysis provide a reference case for testing Burhān's methodological execution, reproducibility, and audit trail. New studies — including the Hayat Tayyibah wellbeing–productivity research — follow only after the engine has been validated against this known case.** Nothing in the engine may reference any specific study.

---

## 14. Success Criteria

**Certification gate (before the first validation run):**
- 100% detection of all defined planted defects in the certification suite.
- Preparation-stage dual-implementation agreement: zero unexplained cell differences on golden data.
- Benchmark replication: published worked examples reproduced within tolerance across measurement, structural, and mediation stages; cross-engine parity map established and documented.
- Full test suite green with production-grade coverage discipline.

**Phase 1 acceptance (per study):**
- Run completes headlessly after the validated study contract, with no human intervention on operational decisions; protected decisions, if triggered, surface only as recommendations or Method Advisories.
- All invariants pass; N reconciliation sums exactly.
- Both review gates passed within bounded retries.
- Re-run from the archived config reproduces identical outputs.
- Every number in the findings draft resolves to a results-store ID (automated check).
- `METHOD_COMPLIANCE_CHECKLIST.md` shows the full playbook sequence evidenced; `DECISION_LOG.md` accounts for every policy decision taken, including the estimator determination.
- The complete output package — including the SPSS/AMOS validation pack, disclosure, and supervisor pack — is produced without any dependency on Phase 2 or Phase 3 components.

---

## 15. First Validation Run — The Completed DBA Study

The first validation run is the researcher's completed DBA study. This study is deliberately selected because it has already been analyzed manually and its methodology is fully documented, giving Burhān a real reference case with known points of comparison: data cleaning decisions, analytical sample, measurement model results, structural paths, mediation outcomes, hypothesis decisions, tables, and findings narrative.

**What Burhān takes from the completed study is its approved methodology — the framework, model, structure, the designed instrument mapping, and thresholds — not its numeric results and not its manually retained item subset.** The contract for this run encodes the instrument as designed; the researcher's own item-retention and item-deletion decisions enter the reference comparison set instead, so the run independently re-derives which items survive under the playbook's governance and shows where its decisions differ. The prior manual analysis is a reference for comparison, not ground truth: manual work can contain calculation errors, item-handling errors, or reporting inconsistencies, and detecting exactly such issues is part of this run's value.

**The purpose of the first run is not to discover new findings, but to certify that Burhān can independently execute, explain, and audit a completed academic analysis with full provenance.** Any divergence between Burhān and the prior manual analysis is treated as a validation signal with no side presumed correct: either Burhān exposes an earlier manual weakness, or the engine/policy requires correction. In both cases, the comparison strengthens the system before it is used on a new study. Divergences are recorded in a reference comparison report, investigated, classified accordingly, and resolved before production use. Because the run re-derives the measurement model from the raw data under the playbook, its measurement audit — loadings, reliability and validity at both construct levels, item-level diagnostics, and item-to-construct content checks — also provides direct evidence for any construct and item revisions the study's supervision may require.

**Minimum deliverables of the first validation run (Stage 1A scope):**
- Validated `study_config.yaml` for the DBA study.
- Cleaned analytical dataset with exact N reconciliation.
- CFA results, including the higher-order measurement structure.
- Structural model results.
- Mediation/moderation results where applicable.
- Hypothesis testing matrix.
- `DECISION_LOG.md`, `FLAGS.md`, and the reproducibility manifest.
- Reference comparison report against the prior manual analysis.

The findings chapter, supervisor pack, and remaining Stage 1B outputs follow once the statistical core is trusted on this known case. **After the DBA validation run is complete, Burhān may be applied to new research projects such as the Hayat Tayyibah wellbeing–productivity study.**

---

## 16. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| LLM misreads the study document (wrong mapping, missed reverse-coding, wrong declared method, wrong higher-order structure) | Strict schema validation; data-dictionary cross-check; Review Gate 1 audit against the source; sign-flip and coverage invariants; hard failure on ambiguity; optional 5-minute config review |
| Study document itself is incomplete or inconsistent with the dataset | Autonomy begins only at the validated contract; contract-stage ambiguity or data–document mismatch is a hard failure with a precise report, never a guess |
| System oversteps into method-owner territory | Protected Decisions Registry is architectural, not advisory — no code path executes a paradigm change, hypothesis change, construct change, or (by default) item deletion |
| Reliability-chasing item deletion becomes p-hacking | Protected by default; where pre-authorized: one-at-a-time protocol, dual trigger, three-item floor, validated-instrument flagging, full before/after audit |
| ML estimation challenged on ordinal Likert data | Ordinal indicator governance: playbook conditions for continuous treatment, MLR where justified, WLSMV/polychoric where required, estimator rationale logged every run |
| Improper missing-data treatment inflates or biases results | Mechanism testing before treatment; FIML/MI only; mean substitution and synthetic cases prohibited by construction; exact N reconciliation |
| Cross-engine verification overpromises package equivalence | Authoritative-engine model: lavaan owns estimation; Python verifies within a certified parity map; unsupported areas declared in FLAGS, never forced |
| Engine trusted before it is proven | Validation-first sequence: certification suites, published benchmarks, then independent re-analysis of the researcher's completed DBA study before any new research |
| Policy blind spot produces a defensible-but-wrong choice | Decision log makes every choice visible; policy is versioned and improves per study; flags rank anything unusual |
| Findings prose overstates results | Statistic-reference drafting with render-time injection; automated checker fails unresolved numbers; Review Gate 2 audits claims against the results store |
| Non-reproducible results | Seeds, lockfiles, config hashing, playbook versioning, run archiving; re-run identity is an acceptance criterion |
| Academic integrity exposure | Method-owner policy and registry = researcher-owned methodology; provenance chain plus formal `AI_USE_DISCLOSURE.md` and supervisor pack make the system's role fully transparent |

---

## 17. Future Evolution

Burhān Phase 1 is personal research infrastructure. Its architecture deliberately supports later moves, none of which is a Phase 1 commitment:

1. **Strategic Gears research-ops asset** — the proven engine wrapped in a service layer (API + light frontend) for client research, education-linked ventures, or internal knowledge products. CLI-first now makes this a wrapping exercise, not a rebuild.
2. **Playbook library growth** — Phase 2 quantitative extensions and Phase 3 assisted qualitative playbooks added behind the same policy, verification, review, and provenance framework, each versioned and certified before use.

---

## 18. Build Approach (Summary)

Built on the researcher's standard two-agent protocol: Codex directs and reviews (approve/reject with exact fixes), Claude Code implements, the researcher coordinates. Estimated Phase 1 scope: 10–14 modules, each with a task contract and acceptance criteria, delivered stage-gated in the 1A → 1B order. The module decomposition, task contracts, `decision_policy.yaml` template, Protected Decisions Registry schema, playbook schema, and repository scaffold are separate documents produced after this concept is approved.

---

*Burhān — برهان — demonstrative proof. The system exists so that every finding it produces can meet that standard: executed by an approved playbook, verified through independent chains, proven first on a known case, decided by declared rules, bounded by human sovereignty over theory, and reproducible on demand.*
