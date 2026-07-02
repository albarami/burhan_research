# Burhān — Playbook Conventions (docs/06_playbooks/PLAYBOOK_SCHEMA.md)

**Status:** For review · **Governed by:** Concept §4, `02_REQUIREMENTS.md` FR-1301–1304 · **Formal contract:** `playbook.schema.yaml`

A playbook is the method owner's adopted position within the accepted literature, codified as an executable specification (Concept §4). It is the *curriculum*; the engine is the *executor*. Every playbook file validates against `playbook.schema.yaml` at load; an invalid or missing playbook is a clean refusal — no playbook, no run (FR-1302).

## The playbook ↔ policy split

Two files govern a run, and the boundary between them is principled:

- **The playbook owns methodology** — the stage sequence, the diagnostic set, the *quality thresholds adopted from the literature* (loading targets, α/CR/AVE, HTMT ceiling, fit bands, MI significance floor, deletion floor), the required citations, and the reporting standard. Playbook content answers "what does the discipline require, in the position we have adopted?"
- **`decision_policy.yaml` owns operations** — the *numeric operating parameters* that tune execution without changing methodology (inclusion percentage, outlier criteria values, imputation selection, bootstrap resamples, respecification cap count, gate retry budget). Policy content answers "how does this machine run it?"

Where a playbook criterion's number is operational rather than methodological, the criterion carries a `policy_ref` and the number lives in policy. Where the number *is* the methodological position (e.g., AVE ≥ 0.50), it lives in the playbook with its citation. A reviewer challenging a threshold should find it in exactly one place, with its literature key attached.

## Compliance derivation (FR-1106)

`METHOD_COMPLIANCE_CHECKLIST.md` is generated from the playbook's `steps`: one row per step, status **completed / failed / flagged**, with the step's `outputs` prefixes checked against what actually landed in the results store. The checklist therefore proves the approved sequence was executed — it is derived evidence, not a hand-written claim.

## Failure semantics per step

`failure_action` maps a criterion breach to the engine's failure taxonomy (`03_ARCHITECTURE.md` §7): `halt` → integrity halt; `flag` → FLAGS entry, continue; `advisory` → Method Advisory path (FR-1203); `recommend` → surface a protected-decision recommendation (e.g., item deletion, FR-705); `report` → recorded outcome only (e.g., fit bands are reported and interpreted, not auto-"fixed").

## Versioning

Playbooks are immutable per version: `CB_SEM_PLAYBOOK_v1.0.yaml` never changes once `status: approved`; changes create `v1.1` with a changelog line. The version and hash enter every run manifest (NFR-102), so evolving positions can never silently alter past results.

## Files

| File | Role |
|---|---|
| `playbook.schema.yaml` | formal contract every playbook validates against |
| `CB_SEM_PLAYBOOK_v1.0.yaml` | Phase 1 CB-SEM playbook (the researcher's adopted positions) |
| `PLS_SEM_PLAYBOOK_v*.yaml` | Phase 2 (reserved) |
| `THEMATIC_ASSISTED_v*.yaml` | Phase 3, assisted (reserved) |
