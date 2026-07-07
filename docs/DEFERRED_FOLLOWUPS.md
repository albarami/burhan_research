# Deferred Follow-ups

Tracked technical debt and hardening deliberately deferred (not skipped) so it
stays recoverable. Each entry is accepted by the coordinator as a non-blocker
for the milestone in which it was raised, with an explicit path to close it.

| ID | Title | Status | Raised | Owner |
|----|-------|--------|--------|-------|
| DF-001 | Node A prompt-coverage meta-test: exhaustive type-row negative controls | OPEN | 2026-07-07 | researcher |

---

## DF-001 — Node A prompt-coverage meta-test: exhaustive type-row negative controls

**Status:** OPEN — Raised 2026-07-07 — Owner: researcher

**Context.** M6 §7 conformance closure was accepted with 6/81 enumerated
prompt-coverage gaps fixed and 0 GAP in the enumerator
(`tests/unit/contract/prompt_coverage.py`); the prompt covers every schema
constraint and gates are green (1132 passed, 99% coverage). During review the
reviewer noted that the standing meta-test's negative-control coverage does not
yet catch a prompt regression on certain schema `type` rows (e.g.
`scale.labels`, `metadata_columns`, `ignored_item_columns`) — removing their
prompt phrases reopens zero rows — and that the `EXCLUDED` rationale for
`type:string` is imprecise (it is treated as trivially satisfied rather than
proven covered per exact path).

**Why deferred.** This hardens the guard-of-the-guard: it strengthens the
meta-test that protects the Node A prompt, not Node A itself. It does NOT affect
whether Node A produces a schema-valid, provenance-authentic `study_config`.
Every schema constraint is already covered and the enumerator reports 0 GAP, so
this is not an M6 correctness blocker.

**To close.**
1. Map every schema `type` row to a context-specific prompt phrase, or prove
   coverage per exact path (rather than an `EXCLUDED` class rationale).
2. Add failing-on-reopening negative controls for `scale.labels`,
   `metadata_columns`, and `ignored_item_columns` (deleting their phrase must
   reopen exactly their row).
3. Correct the `type:string` exclusion rationale (make it precise, or replace it
   with per-path coverage).

**Scope when resumed:** prompt + tests/enumerator only. No schema, validator,
loader, certification, or statistics changes.
