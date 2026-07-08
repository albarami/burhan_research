# TC-18 — PLAN v1 (Qualtrics multi-header crosswalk fix, M6 ingest)

**Contract:** `docs/09_task_contracts/TC-18.md` (ISSUED) · **Branch:** `tc/tc-18-qualtrics-multiheader`
**This is PLAN v1 — no implementation, no extraction, no `--confirm`.** Pause for reviewer approval.

---

## 0. Grounding (read from the actual schema/code, not restated from the contract)

- **Schema** `schemas/study_config.schema.yaml`, `data` block: `header_rows: {type: integer, 1–3}`, `export_dialect: {enum: [qualtrics, generic]}`, and **no code-row-index field**. The contract can express the header *count* and the *dialect*, but not *which* row carries embedded codes.
- **`src/burhan/contract/crosswalk.py`**:
  - `:71` `header_rows = config.data.header_rows if config.data.header_rows is not None else 1` — silent default to **1**.
  - `:99` `codes = rows[0]` (column identifiers); `:100` `texts = rows[1] if header_rows >= 2 else rows[0]` (the code-bearing row — a hardcoded index, not a concatenation); `:101` `data_rows = rows[header_rows:]`.
  - `_match_items` (174–214) scans **`texts`** for modeled item codes with the whole-token regex `(?<![A-Za-z0-9_]){code}(?![A-Za-z0-9_])`; multi-column or multi-code → ambiguity halt; none → FR-104 structural mismatch.
  - `_account_roles` (217–276) assigns `id_column`, `consent_column`, `completion.*`, `attention_checks[].column`, `demographics[].column_hint`, `metadata_columns[]`, `ignored_item_columns[]` by **exact identity against `rows[0]`** (`assign`, :227 `if column not in codes: halt`).
- **`src/burhan/cli/live.py`**: `live_extract` (:195) resolves the export to `_export` (unused, :201) and calls `NodeA.extract` with **no `export_path`** (:217–221). Node A never reads the export; V6 defers to Gate 1 (`validators.py:271` runs V6 only when `export_path is not None`).
- **DBA `study_config.yaml`**: `data.header_rows` absent, `data.export_dialect` absent; `demographics[].column_hint = D1..D13`, `ignored_item_columns = [R1, R2, …]` — **dictionary/item codes, not the export's row-0 Qualtrics QIDs**.
- **Existing fixture** `tests/fixtures/exports/adoption_3header.csv` + `tests/unit/ingest/ingest_util.py::fixture_config`: row 0 = QIDs/semantic names (`ResponseId,Q3,Q4_1,…,Q42,…`), row 1 = question text with embedded item codes (`RS1 - …`), row 2 = ImportId JSON, then data. The config sets `export_dialect: qualtrics` **and** `header_rows: 3`, declares **modeled items by embedded row-1 code** but **non-modeled roles by literal row-0 name** (`ResponseId`, `Q3`, `Q42`, `Progress`, `Finished`, `StartDate`). This is exactly why the current suite is green and never exercised (i) the default-to-1 path or (ii) embedded-code role resolution.

## 1. Mechanism recommendation — **(b) crosswalk dialect handling** (lower-risk *and* the only complete fix)

The contract leaves (a) Node A extracts `header_rows` vs (b) crosswalk detects/validates the dialect open. **Recommend (b)**, with three reasons from the actual code:

1. **Node A structurally cannot author the export's column identifiers.** `live_extract` gives Node A no `export_path`; the prompt forbids respondent data. Node A sees only the study document + data dictionary, which name items/demographics/ignored sections by **dictionary code** (`D1`, `R1`, `R3`) — never the export's row-0 Qualtrics QIDs (`Q5_1`…). The dictionary-code → export-column mapping exists **only** in the embedded row-1 text and can only be recovered at ingest. ⇒ the **secondary** fix (roles by embedded code) *must* live in the crosswalk; mechanism (a) cannot solve it at all.
2. **The schema can't express the code row anyway.** It carries `header_rows` (count) and `export_dialect`, but no code-row-index; `texts = rows[1]` is already hardcoded in the crosswalk. Mechanism (a) would buy only the header *count* — at the cost of reopening the Node A prompt (keeping the prompt-coverage meta-test + DF-001 green) **and** a live re-extraction (a new Node A token) — and would *still* need the crosswalk change for roles.
3. **(b) is single-module and churn-free.** The entire fix stays in `crosswalk.py` + tests: no prompt change, no schema change, no token, and it preserves the existing `study_config.yaml`.

So (a) is strictly costlier and still incomplete; (b) is recommended.

## 2. Primary fix — header-row resolution (no silent default; AT-M18-4)

Replace the `else 1` default with an explicit precedence in `build_crosswalk`:

1. **Contract wins:** if `config.data.header_rows` is set → use it (authoritative; unchanged for the existing fixtures, which set 3).
2. **Dialect detection when unset:** if `config.data.export_dialect == "qualtrics"` **or** the export's row 2 matches the deterministic Qualtrics ImportId signature (every cell parses as JSON containing `"ImportId"`) → `header_rows = 3`, codes = row 0, text = row 1.
3. **Unambiguous single-header:** if unset, no multi-header dialect signature, and the frame is consistent with one header row → `header_rows = 1` (preserves generic-CSV behavior).
4. **Otherwise halt typed** — a multi-header-looking export whose structure can't be established raises `IntegrityHalt` ("header structure unstated/ambiguous for a multi-header export") rather than silently assuming 1 (AT-M18-4).

The exact signature predicate (JSON-with-`ImportId` in row 2) is the leading candidate; finalized in implementation. Note this makes the previously-silent default an explicit, tested decision.

## 3. Secondary fix — role/column resolution from embedded codes (hybrid resolver)

Generalize both `_match_items` and `_account_roles` to resolve **every declared code** (modeled items **and** non-modeled role columns) through one deterministic resolver that maps a declared token → a single row-0 column by:

- **literal row-0 identity** (the token *is* a row-0 name — the current behavior, keeps `ResponseId`/`Q42` working), **or**
- **embedded row-1 code** (the token appears, whole-token, in exactly one row-1 text cell — the new behavior, resolves `D1`/`R1` to their QID columns).

Invariants preserved (V6 strictness unchanged, AT-M18-3):
- a token resolving to **>1** column (by either route, across columns) → ambiguity halt;
- a column embedding **>1** declared code → ambiguity halt;
- a declared token resolving to **0** columns → structural-mismatch halt;
- after resolution every export column still maps to **exactly one** role; a genuinely undeclared column is still an orphan halt.

This is additive: the adoption fixture's literal-row-0-name roles keep resolving (AT-M18-6), and the DBA embedded-code roles now resolve. `column_hint` (required on demographics) is fed through the same resolver (literal-or-embedded), so `Q42` and `D1` both work.

## 4. DBA path after TC-18 — existing `study_config.yaml` stays valid ⇒ **direct `--live --confirm` Gate 1**

Under (b) nothing in the contract changes. The persisted `study_config.yaml` already passed schema + V1–V5 + V7 + FR-204 at extraction; the fixed crosswalk then (i) auto-detects the Qualtrics dialect (header_rows→3), (ii) resolves modeled items from row 1, and (iii) resolves the embedded-code roles (`D1…`, `R1`, `R2`, ignored C/T) from row 1 → all columns account → **V6 passes**. So **no re-extraction and no new Node A token** — proceed straight to `--live --confirm` Gate 1.

Two assumptions the implementation/Gate-1 run must confirm (both already asserted by the contract):
- every declared non-modeled code (`D1..D13`, `R1`, `R2`, ignored items) is embedded **exactly once** in row 1 (contract §Why item 2 states this is verified; the fixture models it, AT-M18-2 tests it, the real run re-confirms it);
- `_resolve_inputs` picks the real CSV via `sorted(glob("*.csv"))[0]`, so the `data.file: survey_responses.csv` vs `_AI Readiness….csv` name mismatch is inert to V6 (the separate `_resolve_inputs` item the contract scopes **out** unless it blocks the fixture test).

Reviewer confirms "direct Gate 1 vs re-extraction" at DoD per the contract; PLAN v1's position is **direct Gate 1, no re-extraction**.

## 5. AT-M18-1..6 → concrete tests / fixtures

All in `tests/unit/ingest/test_crosswalk.py` (siblings of AT-M05), reusing `ingest_util`. New fixtures under `tests/fixtures/exports/`, all **synthetic** (never the researcher's raw data). A new `ingest_util.dba_fixture_config()` mirrors the DBA convention (roles declared by embedded code; no `header_rows`).

| AT | Test name (new) | Fixture | Asserts |
|----|-----------------|---------|---------|
| **AT-M18-1** modeled items resolve | `test_multiheader_modeled_items_resolve_without_header_rows` | `dba_multiheader.csv` (3-header; row1 embeds modeled + role codes) + `dba_fixture_config()` (no `header_rows`) | `column_to_item` complete, `missing_items` empty; dialect auto-detected |
| **AT-M18-2** all roles resolve | `test_multiheader_embedded_role_codes_resolve` | `dba_multiheader.csv` | demographics (`D1…`), ignored (`R1,R2`), metadata declared by embedded code resolve to their row-0 columns; no "declared column the export lacks" halt |
| **AT-M18-3** zero-orphan preserved | `test_multiheader_undeclared_column_still_orphans` | `dba_multiheader_orphan.csv` (one extra undeclared column) | `IntegrityHalt` names the orphan; declaring it (metadata/ignored) then passes — V6 strictness intact |
| **AT-M18-4** ambiguity halts, no silent default | `test_multiheader_unstated_ambiguous_headers_halt` | `dba_multiheader_nosignature.csv` (multi-header shape, ImportId row removed, `header_rows`/`export_dialect` unset) | typed `IntegrityHalt`; does **not** silently parse as `header_rows=1` |
| **AT-M18-5** single-header still works | `test_single_header_plain_csv_resolves` | `plain_single_header.csv` (codes as literal row-0 headers) + config with `header_rows: 1` | resolves correctly; no regression for non-Qualtrics exports |
| **AT-M18-6** no drift | (suite run, not one test) | — | full `test_crosswalk.py` AT-M05-1..4 stay green (adoption literal-row-0 roles still resolve under the hybrid resolver); `tests/unit/contract/test_prompt_schema_coverage.py` + DF-001 untouched (no prompt/schema change); full gate suite green |

**Secondary-fix coverage is explicit:** AT-M18-2 (embedded-code roles resolve) + AT-M18-3 (orphan integrity under the new resolver) together cover the role-accounting fix; AT-M18-6 guards that the literal-row-0-name convention (AT-M05-1) does not regress.

## 6. File-by-file change list (implementation phase, for reference only)

- `src/burhan/contract/crosswalk.py` — header-row resolution (§2) + unified hybrid resolver feeding `_match_items` and `_account_roles` (§3). No signature change to `build_crosswalk(export_path, config)`; `v6_column_accounting` untouched.
- `tests/unit/ingest/test_crosswalk.py` — AT-M18-1..5 tests (§5).
- `tests/unit/ingest/ingest_util.py` — add `dba_fixture_config()` (embedded-code roles, no `header_rows`).
- `tests/fixtures/exports/` — new synthetic fixtures: `dba_multiheader.csv`, `dba_multiheader_orphan.csv`, `dba_multiheader_nosignature.csv`, `plain_single_header.csv`.
- **No** change to schema, prompt, `study_config.yaml`, validators, `live.py`, or `_resolve_inputs`.

## 7. TDD order (one PR, standards §6)

1. Add fixtures + `dba_fixture_config()`.
2. RED: AT-M18-1..5 (fail against current `crosswalk.py`).
3. GREEN: header-row resolution (§2), then the hybrid resolver (§3), minimally.
4. Confirm AT-M18-6: full `test_crosswalk.py`, `test_prompt_schema_coverage.py`, and the whole gate suite green.
5. Gates: `ruff · format · mypy · pytest+coverage · lintr`.

## 8. Guardrails / out-of-scope (from the contract)

- V6/zero-orphan strictness **unchanged** — only the matching mechanism is corrected (AT-M18-3 is the guardrail).
- No schema change, no Node A prompt change (so the prompt-coverage meta-test and DF-001 stay intact), no hand-edit of the DBA `study_config.yaml` or raw CSV.
- `_resolve_inputs` CSV selection is a **separate** known item — noted, not fixed here unless it blocks a fixture test (it does not; fixtures pass paths directly).

## 9. Self-audit / risks

- **Regression risk (highest):** the hybrid resolver must keep AT-M05-1's literal-row-0-name roles resolving. Mitigation: literal-identity remains the first route; embedded-code is additive; AT-M18-6 runs the full existing suite.
- **Detection false-negative:** a Qualtrics export missing the ImportId row with `header_rows`/`export_dialect` unset → halts (AT-M18-4), which is the safe outcome; the real DBA export has the ImportId row and (per contract) is detectable.
- **Assumption:** all non-modeled DBA codes are embedded once in row 1 (§4) — asserted by the contract, re-confirmed at Gate 1.
- **No token, no data touch:** the plan spends nothing and reads no respondent data; fixtures are synthetic.

## 10. Hold

PLAN v1 only. Awaiting reviewer approval before any implementation. No push, no implementation PR, no extraction, no `--confirm`.
