# Higher-order CFA benchmark — provenance (AT-M10-1; FR-701/702/1502)

**Published worked example:** Muthén, L. K., & Muthén, B. O. *Mplus User's
Guide* (8th ed.), Example 5.6 — "CFA with a second-order factor".

- **Data:** `ex5.6.dat` — 500 observations × 12 variables (y1–y12),
  downloaded verbatim from the publisher:
  https://statmodel.com/usersguide/chap5/ex5.6.dat (fetched 2026-07-03).
- **Published output (reference values):**
  https://statmodel.com/usersguide/chap5/ex5.6.html — full Mplus output.
- **Model:** f1 =~ y1–y3 · f2 =~ y4–y6 · f3 =~ y7–y9 · f4 =~ y10–y12 ·
  f5 =~ f1 + f2 + f3 + f4 (marker scaling).

**Printed reference estimates (unstandardized, marker-fixed):**

| Parameter | Published | Parameter | Published |
|---|---|---|---|
| f1 =~ y2 | 0.760 | f3 =~ y8 | 0.702 |
| f1 =~ y3 | 0.669 | f3 =~ y9 | 0.691 |
| f2 =~ y5 | 0.718 | f4 =~ y11 | 0.742 |
| f2 =~ y6 | 0.703 | f4 =~ y12 | 0.669 |
| f5 =~ f2 | 0.944 | f5 =~ f3 | 1.168 |
| f5 =~ f4 | 0.854 | χ² (df=50) | 46.743 |

**Cross-engine reproduction (FR-1502):** lavaan 0.6-20 (renv-locked)
reproduces every printed value to the printed precision (verified
2026-07-03 before the benchmark tests were written). α/CR/AVE reference
values for both levels come from `semTools` (renv-locked version) on the
same fit — the same reference-implementation pattern AT-M10-2 mandates
for HTMT and Fornell–Larcker.
