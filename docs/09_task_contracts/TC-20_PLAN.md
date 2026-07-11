# TC-20 — PLAN v1: Qualtrics demographic crosswalk (selected-choice + text-sidecar)

| | |
|---|---|
| **Contract** | `docs/09_task_contracts/TC-20.md` (ISSUED) |
| **Branch** | `tc/tc-20-demographic-crosswalk` |
| **Scope wall** | `src/burhan/contract/crosswalk.py` + `tests/unit/ingest/test_crosswalk.py` (+ helper `ingest_util.py`, + new synthetic fixtures under `tests/fixtures/exports/`) **only** |
| **State** | PLAN v1 — **no implementation**; hold for review |

> **This plan authorizes no edits to** the study schema (`schemas/study_config.schema.yaml`), the Node A prompt, `live.py`, statistical modules, governed docs, `renv.lock`, the DBA `study_config.yaml`, or the raw CSV. The code fix lives entirely in the crosswalk's demographic role-accounting seam + its tests. The **D4/D10 study-source correction is a governed data step (researcher-led), performed after this code merges and re-extracted through the live path — it is not part of this code PR** (§4).

---

## 1. Root cause (recap, from the approved read-only diagnosis)

Against the real 3-header Qualtrics export the `prep` crosswalk halts `declared column resolves to more than one export column (FR-103/104)` (`crosswalk.py:324`). `_account_roles` resolves each demographic by `resolve(demographic.column_hint, ROLE_DEMOGRAPHIC)`; `_resolve_column` (`crosswalk.py:234`) matches a token by **literal row-0 id** (`column == token`) **or whole-token embedding in the row-1 text** (`_embeds`, `crosswalk.py:229`). The demographic code `D3` embeds in the row-1 text of **both** its Qualtrics selected-choice column `Q44` (`"D3. …education level? - Selected Choice"`) **and** the paired `Q44_5_TEXT` "Other (please specify)" free-text sidecar (`"D3. … - Other (please specify) - Text"`) → 2 hits → halt. `D5`/`D7` share the pattern. Two adjacent source-contract facts (`D4` nationality carries no `D4` label in the export; phantom `D10` the export never had) are separate and handled in §4.

## 2. Mechanism — selected-choice + `_TEXT` sidecar resolution (applied only after PLAN approval)

The change is confined to **demographic** role accounting; `resolve()` for id/consent/completion/attention/metadata/ignored stays byte-for-byte strict. Two module-level helpers + a demographic-specific resolver replace the single `resolve(demographic.column_hint, ROLE_DEMOGRAPHIC)` line (`crosswalk.py:352-353`).

**Deterministic sidecar detection (dual signal, both required — conservative):**
```python
_SIDECAR_ID  = re.compile(r"^(?P<base>.+)_\d+_TEXT$")   # Qualtrics "…_N_TEXT" companion id
_TEXT_MARKER = re.compile(r"-\s*Text\s*$")              # row-1 "…- Other (please specify) - Text"

def _text_sidecars_of(base: str, codes, texts) -> list[str]:
    """Columns that are the Qualtrics free-text companion of `base`:
    id == f'{base}_<N>_TEXT' AND row-1 text ends '- Text'. Deterministic, language-anchored."""
    out = []
    for col, text in zip(codes, texts, strict=True):
        m = _SIDECAR_ID.match(col)
        if m and m["base"] == base and _TEXT_MARKER.search(text):
            out.append(col)
    return out
```

**Demographic resolution (replaces the one-liner):**
```python
for demographic in data.demographics or []:
    token = demographic.column_hint
    hits = _resolve_column(token, codes, texts)          # unchanged matcher
    hit_set = set(hits)
    # collapse: drop each hit that is the *_TEXT companion of another (co-hit) base column
    bases = [c for c in hits
             if not (( m := _SIDECAR_ID.match(c)) and m["base"] in hit_set
                     and _TEXT_MARKER.search(texts[codes.index(c)]))]
    if len(bases) == 0:
        halt FR-104  "contract declares a column the export lacks"   # (token, role=demographic)
    if len(bases) > 1:
        halt FR-103/104  "declared column resolves to more than one export column"  # columns=sorted(bases)
    base = bases[0]
    claim(base, ROLE_DEMOGRAPHIC)
    for sidecar in _text_sidecars_of(base, codes, texts):
        claim(sidecar, ROLE_IGNORED)                     # "Other-specify" free-text; not analyzed
```

**Why this is correct and non-weakening:**
- **`D3`/`D5`/`D7` (code-labelled choice + own text sidecar):** hits `[Q44, Q44_5_TEXT]` → `Q44_5_TEXT` is the `_TEXT` companion of co-hit `Q44` → dropped → single base `Q44` → bind demographic; `_text_sidecars_of("Q44")` re-finds `Q44_5_TEXT` → account **ignored**.
- **`D4` (unlabelled choice, literal-id hint `Q45`):** hits `[Q45]` (its sidecar `Q45_2_TEXT` does **not** embed `Q45` and `Q45 != Q45_2_TEXT`, so it is *not* a hit) → single base `Q45` → bind; `_text_sidecars_of("Q45")` finds `Q45_2_TEXT` **by base-pairing** → account ignored. The sidecar is accounted even though it was never a hit — this is why accounting keys off the **resolved base id**, not the hit set.
- **Real ambiguity preserved (AT-M20-2):** two *non-sidecar* matches (e.g. `D1` → `Q40` + `Q99`, neither a `_N_TEXT` companion) → `bases` keeps both → **halt FR-103/104** naming both. This is exactly the retained TC-18 test `test_multiheader_embedded_role_token_ambiguous_halts_naming_columns` (`columns == ["Q40","Q99"]`) — it must stay green.
- **Zero-orphan preserved (AT-M20-5):** a `_TEXT` column not paired to any *declared demographic base* is never auto-claimed → stays an orphan → V6 halt. `claim()`'s existing double-claim guard still fires if a sidecar id collides with a modeled/other-role column (a genuine conflict halts, correctly).
- **Missing column preserved (AT-M20-4 / FR-104):** `len(bases) == 0` still halts — a declared demographic the export lacks is never silently dropped.

## 3. Column-hint consumption — decision

`Demographic` is `{code, column_hint, type}` with schema `additionalProperties: false` (`models.py:530`, `study_config.schema.yaml:189-194`) — **no new per-demographic field is possible without a schema change, which is out of scope.** `column_hint` therefore remains the sole binding lever, consumed **unchanged** by `_resolve_column` as a **deterministic whole-token match** resolving to a column that is **either (a) a literal row-0 column id** (`column == token`) **or (b) a whole-token embedding in the row-1 question-text row** (`_embeds`, bounded by non-alphanumeric/underscore). It is **not** an alias table, substring, fuzzy, or positional match.

- `D3`/`D5`/`D7`/`D6`/`D8`/`D9`/`D11`/`D12`/`D13` use form **(b)** — the logical code embedded in the code-prefixed row-1 text (`"D3. …"`).
- `D4` uses form **(a)** — the literal row-0 id `Q45` — because its row-1 text (`"What is your nationality?"`) carries no code token; this hint is supplied by the corrected study source (§4).

TC-20 adds **no new hint syntax and no schema field**; it only post-processes the resolved column set for the choice/sidecar collapse in §2.

## 4. D4 / D10 path — decision + non-weakening proof

**Decision: D4 and D10 require a governed study-source correction + re-extraction. The existing `study_config.yaml` does NOT stay valid for a direct `--confirm`.**

Rationale (both are *unresolvable with the current config*, and the config cannot be hand-edited — `live.py:225` write-back + `live.py:259` glance-token sha guard clobber/halt any manual edit):
- **D10 (phantom):** `column_hint "D10"` → 0 export columns → FR-104 halt. The **only** non-weakening resolution is to **remove D10 from the declared demographics**. Tolerating a declared-but-absent column would weaken FR-104 — forbidden. Removal must come from the corrected study source (Node A stops emitting D10), via re-extraction.
- **D4 (nationality):** `column_hint "D4"` → 0 export columns (no `D4` token in the export text). It needs a resolvable hint = the **literal row-0 id `Q45`**. Node A cannot synthesize `Q45` (it never sees the export — `ALLOWED_INPUTS = (study_document, data_dictionary)`, `node_a.py:122`), so the corrected study source must drive Node A to emit `column_hint: "Q45"`. **Implementation step 0 (read-only):** confirm the `data_dictionary.docx` carries the nationality↔`Q45` mapping so Node A can emit the literal id; if it cannot, escalate to the researcher for the exact source-correction form (a governed decision) before proceeding.

**Non-weakening proof (the reviewer's explicit requirement).** TC-20 does **not** keep a config that declares a phantom `D10`; `D10` is removed *at the source*, so FR-104's missing-column strictness is never relaxed — and this is **proven by AT-M20-4's negative control**: a config that *still* declares `D10` against the skipped-number export **still halts FR-104**. The §2 change is a strictly **narrower** resolution of one Qualtrics structure (a choice column + its own `_N_TEXT` companion), never a relaxation of any guard: real 2-base ambiguity still halts (AT-M20-2 + retained TC-18 `dba_multiheader_ambiguous_role`), unpaired/undeclared columns still orphan (AT-M20-5), missing columns still halt (AT-M20-4). No guard is loosened.

**Division of labour:** the §2 crosswalk change (this code PR) resolves `D3`/`D5`/`D7` and makes a literal-id demographic (`D4`→`Q45`) + its sidecar resolve. The **D4/D10 source correction + governed re-extraction is a separate researcher-led data step** performed after merge (I do not edit the `.docx` study inputs or the `study_config.yaml`); then the `--live --confirm` run is repeated.

## 5. Acceptance tests → concrete tests, fixtures, assertions

All tests extend **`tests/unit/ingest/test_crosswalk.py`** using the existing `dba_fixture_config(mutate)` helper (`ingest_util.py`) and new committed 3-header fixtures under `tests/fixtures/exports/` modeled on `dba_multiheader.csv` (synthetic header rows + a few dummy data rows; **never raw respondent data**, standards §7). New fixtures carry Qualtrics `ImportId` row-2 signatures so the TC-18 dialect detector resolves `header_rows == 3`.

| AT | Test(s) | Fixture / config | Assertion | RED-first? |
|----|---------|------------------|-----------|:--:|
| **M20-1** selected-choice binds, sidecar ignored | `test_demographic_choice_binds_and_text_sidecar_ignored` | new `dba_demographic_sidecar.csv` (choice `Q44` "D3.…- Selected Choice" + `Q44_5_TEXT` "…- Other (please specify) - Text"); `dba_fixture_config` mutate → `demographics=[{code:"D3",column_hint:"D3",type:"categorical"}]` | `roles["Q44"]=="demographic"` **and** `roles["Q44_5_TEXT"]=="ignored_item"`; no halt | ✅ |
| **M20-2** real ambiguity still halts | (a) retained `test_multiheader_embedded_role_token_ambiguous_halts_naming_columns` (`dba_multiheader_ambiguous_role.csv`, D1→Q40+Q99); (b) new `test_demographic_two_nonsidecar_matches_halt` | (a) existing; (b) fixture where a hint embeds in a choice col **and** an unrelated `_TEXT` col whose base is a *different* column (not paired) | (a) `IntegrityHalt`, `columns==["Q40","Q99"]`; (b) `IntegrityHalt` "more than one" naming both — collapse must **not** fire | guard |
| **M20-3** unlabelled demographic binds (literal row-0 id) | `test_unlabelled_demographic_binds_via_literal_id` | new `dba_demographic_unlabelled.csv` (`Q45` "What is your nationality? - Selected Choice" + `Q45_2_TEXT` "…- Text", **no code in text**); mutate → `demographics=[{code:"D4",column_hint:"Q45",type:"categorical"}]` | `roles["Q45"]=="demographic"` **and** `roles["Q45_2_TEXT"]=="ignored_item"` (sidecar accounted by base-pairing though never a hit); no halt | ✅ |
| **M20-4** removed demographic / skipped number + FR-104 guard | `test_skipped_demographic_number_resolves_when_undeclared` **and** `test_still_declaring_absent_demographic_halts` | new `dba_demographic_skipnum.csv` (`Q50` "D9.…", `Q51` "D11.…", **no D10**); pass-config declares D9,D11; negative-control mutate adds `{code:"D10",column_hint:"D10",…}` | pass: no halt, both bind; negative control: `IntegrityHalt` FR-104 naming `D10` (**proves FR-104 not weakened**) | ✅ (neg-control) |
| **M20-5** zero-orphan preserved | `test_unpaired_text_column_still_orphans` (+ full-accounting positive in M20-1/3) | `dba_demographic_sidecar.csv` variant with an extra `Q77_1_TEXT` **not** paired to any declared demographic base | `IntegrityHalt` V6 orphan naming `Q77_1_TEXT`; declaring it `ignored_item_columns` then passes | guard |
| **M20-6** no drift / no model change | whole prior suite: `uv run pytest -q` (unit + golden + benchmark + integration + prompt-coverage); + `git diff --stat main…` guard | — | all green; existing `test_crosswalk.py` TC-05/TC-18 cases unchanged; diff shows only `crosswalk.py` + ingest tests/fixtures; no `renv.lock`/study-bundle mutation | guard |

## 6. Files touched (implementation phase)

- `src/burhan/contract/crosswalk.py` — add `_SIDECAR_ID`, `_TEXT_MARKER`, `_text_sidecars_of`; replace the demographic branch of `_account_roles` (§2). Nothing else in the module changes (item matching, header resolution, hashing, other roles untouched).
- `tests/unit/ingest/test_crosswalk.py` — add AT-M20-1..5 tests.
- `tests/unit/ingest/ingest_util.py` — a small `dba_demographic_config(mutate)` helper (or reuse `dba_fixture_config` mutate hooks) for the sidecar demographics.
- `tests/fixtures/exports/dba_demographic_sidecar.csv`, `dba_demographic_unlabelled.csv`, `dba_demographic_skipnum.csv` (+ inline `tmp_path` variants for the negative controls where cheaper) — synthetic, value-free.

No governed doc, schema, prompt, `live.py`, statistical module, lockfile, or study bundle.

## 7. Gates (standards §6; all green before completion report)

```bash
uv run ruff check . --no-cache && uv run ruff format --check .
uv run mypy src/
uv run pytest -q --cov=src --cov-report=term     # contract/crosswalk.py stays 100% (its current bar)
uv run burhan doctor                             # environment untouched (post-commit, clean tree)
```
No R sources change → `lintr` no-op. Env per the standing recipe (source `~/.config/burhan/.env` + pins) for `doctor`.

## 8. RED → GREEN execution order (implementation phase)

1. Add committed fixtures + the RED-first tests (M20-1, M20-3; the M20-4 pass-case). Run the file → confirm each **fails for the stated reason** (today: FR-103/104 ambiguity for M20-1; FR-104 zero-hit for M20-3's literal-id case is already resolvable — confirm it is the *sidecar* that currently orphans).
2. Add the guard tests (M20-2 both, M20-4 negative control, M20-5 orphan) → confirm they pass **pre-fix** (guards intact) except the RED-first ones.
3. Apply the §2 change to `crosswalk.py`.
4. Run full gates → all GREEN; guards still hold; the retained TC-18 ambiguity test stays green.
5. Completion report; await Codex verdict. (Merge, then the governed D4/D10 source correction + re-extraction, then re-run `--live --confirm` — per §4 and the contract DoD.)

## 9. Risks / ripples

- **Sidecar accounting adds `ignored_item` roles** — prep drops ignored columns from analysis exactly as today; demographics are non-modeled (FR-202 retention unaffected). AT-M20-6 (full suite + golden) proves no downstream drift.
- **`codes.index(c)` in the collapse** assumes unique row-0 ids — already guaranteed by the duplicate-code halt (`crosswalk.py:104-111`) that runs before role accounting.
- **A sidecar id colliding with a modeled/declared column** double-claims via `claim()` → halts (correct: a genuine conflict, not silently ignored). Noted, not expected in the DBA structure.
- **D4 depends on the source correction** carrying a literal `Q45` hint; step-0 read-only confirmation of the data dictionary de-risks it before code. The crosswalk test (M20-3) proves the *mechanism* independently of the live source.
- **No raw data in fixtures** — every new fixture is synthetic header rows + dummy values; the value-free-report assertions (as in the existing `test_crosswalk_payload_is_canonical_and_value_free`) extend to the new cases.

## 10. Definition of Done

AT-M20-1..6 green; whole prior suite green (incl. retained TC-05/TC-18 crosswalk cases); gates clean; diff limited to `crosswalk.py` + ingest tests/fixtures; FR-103/104 real-ambiguity, V6 zero-orphan, and FR-104 missing-column guards all still halt (M20-2/-4/-5). On Codex APPROVE + merge, the governed D4/D10 study-source correction + re-extraction proceeds (researcher-led), then the `--live --confirm` DBA run is repeated — it should pass `prep` (N-chain) → measurement → structural → effects → `REFERENCE_COMPARISON.md`.
