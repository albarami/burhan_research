# Effects benchmark — provenance (AT-M11-2; FR-802/1502)

**Published worked example:** Muthén, L. K., & Muthén, B. O. *Mplus User's
Guide* (8th ed.), Example 3.16 — "path analysis with continuous dependent
variables, bootstrapped standard errors, indirect effects, and
non-symmetric bootstrap confidence intervals".

- **Data:** `ex3.11.dat` — 500 observations × 6 variables (y1–y3, x1–x3),
  downloaded verbatim from the publisher:
  https://statmodel.com/usersguide/chap3/ex3.11.dat (fetched 2026-07-04;
  sha256 `305188c35a3ffbca7262a954ee6b7f316722430bb9639f11da7d14a701e6cd3e`).
- **Published output (reference values):**
  https://statmodel.com/usersguide/chap3/ex3.16.html — full Mplus output
  (BOOTSTRAP = 1000; MODEL INDIRECT y3 IND y1 x1 / y3 IND y2 x1;
  CINTERVAL(BOOTSTRAP) = percentile).
- **Model:** y1 ~ x1+x2+x3 · y2 ~ x1+x2+x3 · y3 ~ y1+y2+x2; specific
  indirect effects x1→y1→y3 and x1→y2→y3 (no direct x1→y3 edge).

## Printed reference values

| Quantity | Estimate | 95% bootstrap CI (percentile) |
|---|---|---|
| indirect x1→y1→y3 | 0.503 | [0.445, 0.558] |
| indirect x1→y2→y3 | 2.188 | [2.054, 2.310] |
| sum of indirect x1→y3 | 2.691 | [2.567, 2.813] |

Printed path estimates: y1~x1 .992 · y1~x2 2.001 · y1~x3 3.052 ·
y2~x1 2.935 · y2~x2 1.992 · y2~x3 1.023 · y3~y1 .507 · y3~y2 .746 ·
y3~x2 1.046.

## Cross-engine reproduction (FR-1502)

lavaan **0.6-21** (renv-locked), verified 2026-07-04 before the tests
were written:

- **Point estimates are deterministic ML and reproduce every printed
  value exactly at printed precision** (all nine paths and all three
  indirect effects) — pinned with `round(est, 3)` equality.
- **Bootstrap CI bounds are resampling-stochastic**: the published run
  used Mplus's resampler at R = 1000 (percentile); the engine uses the
  renv-locked lavaan resampler at the policy resample count with
  bias-corrected CIs (`bca.simple`, policy `ci_type: bias_corrected`).
  Measured deviations from the published bounds on the verification run
  (seed 1, R = 1000): percentile ≤ 0.008, bias-corrected ≤ 0.013 across
  all six bounds. The benchmark therefore asserts every CI bound within
  **±0.025** of the published value — ≈ 2× the largest measured
  cross-resampler deviation, and far below the smallest CI half-width
  (≈ 0.056) — plus byte-identical reproduction across same-seed runs.

## Engine-path benchmark (run_effects on Mplus UG ex5.11)

The ex3.16 example is an observed-variable path model, which a study
contract cannot express (constructs require ≥ 2 indicators), so it
certifies the R worker directly. The **engine path** is certified on
the published **ex5.11 latent model** (data + printed values:
`tests/unit/stats_structural/PROVENANCE.md`, sha256
`6c238edf…4799d919`) expressed as a study contract: H1–H3 are the
published regressions, H4 hypothesizes the mediation chain the model
implies (F1 → F3 → F4) with **no direct F1 → F4 edge — exactly the
published model**.

- Path estimates reproduce the printed values (.563, .790, .473) at
  printed precision through `run_effects`.
- Indirect F1→F4 = .266 at 3 decimals (= .563 × .473, the product of
  printed estimates; engine full-precision .266291).
- Bootstrap CI for the indirect effect is not printed in the published
  output; the reference is the renv-locked lavaan itself, captured
  2026-07-04 through `run_effects` (seed 1, R = 1000, `bca.simple`):
  **[0.195444, 0.360454]**, pinned within **±0.005** (same-seed draws
  are identical; the margin covers order-statistic sensitivity to
  host floating-point only).
- Classification: direct edge absent → `indirect_only` (Zhao's
  no-direct branch; zhao2010).
