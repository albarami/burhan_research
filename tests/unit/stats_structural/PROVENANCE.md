# Structural benchmark — provenance (AT-M11-1; FR-801/1502)

**Published worked example:** Muthén, L. K., & Muthén, B. O. *Mplus User's
Guide* (8th ed.), Example 5.11 — "SEM with continuous factor indicators".

- **Data:** `ex5.11.dat` — 500 observations × 12 variables (y1–y12),
  downloaded verbatim from the publisher:
  https://statmodel.com/usersguide/chap5/ex5.11.dat (fetched 2026-07-04;
  sha256 `6c238edfbe30c72ac8f289e9bfab2360a7c26f6f15cb92acd984b1a94799d919`).
- **Published output (reference values):**
  https://statmodel.com/usersguide/chap5/ex5.11.html — full Mplus output.
- **Model:** f1 =~ y1–y3 · f2 =~ y4–y6 · f3 =~ y7–y9 · f4 =~ y10–y12 ·
  f3 ~ f1 + f2 · f4 ~ f3 (marker scaling, meanstructure).

## Printed fit reference (Mplus output page)

| Index | Published | Index | Published |
|---|---|---|---|
| χ² | 53.704 | df | 50 |
| p | 0.3344 | CFI | 0.997 |
| TLI | 0.997 | RMSEA | 0.012 |
| RMSEA 90% CI | 0.000 – 0.032 | SRMR | 0.027 |

**Printed structural paths (unstandardized):** f3 ~ f1 = 0.563 ·
f3 ~ f2 = 0.790 · f4 ~ f3 = 0.473.

## Cross-engine reproduction (FR-1502)

lavaan **0.6-21** (renv-locked) reproduces every printed value above to
the printed precision (verified 2026-07-04, before the benchmark tests
were written; full-precision lavaan values: χ² 53.703643, p 0.334353,
CFI 0.997460, TLI 0.996648, RMSEA 0.012172 CI [0.000000, 0.031996],
SRMR 0.027307). The AT-M11-1 tests pin the engine's reported fit to the
printed values at printed precision (`round(observed, 3)` equality; df
exact; p at 4 decimals) — the same cross-host-stable pattern the
AT-M10-1 benchmark uses. Path estimates are pinned to the printed
values; standard errors are not pinned across engines (Mplus and lavaan
use different information-matrix conventions).
