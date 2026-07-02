# Burhān — Schema Contracts (docs/05_schemas/00_README.md)

**Status:** For review · **Governed by:** `02_REQUIREMENTS.md`, `03_ARCHITECTURE.md`

These files are the machine contracts every artifact validates against (FR-203, FR-1001, NFR-402). Runtime pydantic models are generated from / CI-checked against these schemas; divergence between code models and these files fails the build.

## Conventions

- **Dialect:** JSON Schema draft 2020-12. YAML files are JSON Schema expressed in YAML.
- **Strictness:** `additionalProperties: false` everywhere. Unknown fields are defects, not extensions.
- **Versioning:** every instance document carries `schema_version`; schemas carry `$id` with a version suffix. Schema changes bump the version and are recorded in the run manifest hashes (NFR-102).
- **Immutability:** instance files are written once and hashed; corrections mean a new run, never an edit (AD-06).
- **Column accounting (zero-orphan rule):** after the crosswalk, every export column must resolve to exactly one declared role — model item, demographic, consent, id, completion, attention check, `metadata_columns`, or `ignored_item_columns`. An unaccounted column is a hard failure (FR-507).

## Shared enums

- `stage`: `ingest | contract | gate1 | power | prep | assumptions | measurement | structural | effects | robustness | narrate | gate2 | package`
- `engine`: `r_lavaan | py_semopy | py_pandas | orchestrator`
- `run_state`: `PENDING | RUNNING | COMPLETED | COMPLETED_TO_BOUNDARY | HALTED_INTEGRITY | HALTED_VERIFICATION | HALTED_GATE`

## Statistic ID grammar (results store)

```
id        := stage "." family { "." segment } [ "." variant ]
stage     := "power" | "prep" | "assumptions" | "measurement"
           | "structural" | "effects" | "robustness"
family    := lower_snake            # e.g. loadings, path, fit, reliability
segment   := token | path_token
token     := [A-Za-z0-9_]+          # construct or item code from the contract
path_token:= token "->" token       # ASCII arrow; renderers may display "→"
variant   := lower_snake            # e.g. std, unstd, boot_ci, level2
```

Examples: `measurement.loadings.first_order.R_TI.R9.std` · `structural.path.READINESS->PEOU.std` · `effects.indirect.READINESS->INT.boot_ci` · `structural.fit.rmsea`. IDs are unique per run; the store is append-only JSONL with a derived index (AD-05).

## Files

| File | Contract for | Primary FR |
|---|---|---|
| `study_config.schema.yaml` | the validated study contract (Node A output) | FR-201–206 |
| `study_config.example.yaml` | worked example exercising every feature | — |
| `results_store.schema.json` | statistic entries | FR-1001–1003 |
| `provenance_log.schema.json` | sanad log entries | NFR-301 |
| `decision_log.schema.json` | machine-readable decisions behind DECISION_LOG.md | FR-1201 |
| `run_manifest.schema.json` | seeds, hashes, environment, stage record, seal | NFR-100 |
| `reference_comparison.schema.json` | DBA validation comparison report | FR-1503 |

Policy and registry schemas ship with their templates in `docs/07_policy/`; the playbook schema ships with `docs/06_playbooks/`.
