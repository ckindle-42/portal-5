# Tool-Preselect Acceptance Report — Corrected Addendum

**Date**: 2026-07-12  
**Original report**: `TOOLPRESELECT_ACCEPTANCE_REPORT_20260712T170730Z.md`  
**Reason**: `run_bench.py` was counting `no_good_fit` scenarios (where `hit_top_k` is `None` by design) as failures in the OVERALL denominator, deflating both models' headline numbers.

---

## Bug

`hit_top_k` is set to `None` for `no_good_fit` scenarios (15 reps per model) because there is no ground truth to score against — the task that built these explicitly said not to auto-PASS/FAIL them. However, `if None` is falsy in Python, so:

```python
hits = sum(1 for r in cat_results if r["hit_top_k"])  # None counts as 0
```

silently folded 15 unscored reps into the denominator as failures.

---

## Corrected Numbers

| Model | Original OVERALL | Corrected OVERALL | Delta |
|---|---|---|---|
| gemma4:e2b-mlx | 217/294 (73.8%) | **217/279 (77.8%)** | +4.0pp |
| gemma4:e4b-mlx | 261/294 (88.8%) | **261/279 (93.5%)** | +4.7pp |

Per-category numbers are unchanged (the bug only affected the OVERALL aggregation and the `no_good_fit` category row).

---

## Corrected Per-Category (e4b-mlx)

| Category | hit@K | Notes |
|---|---|---|
| Positive | 174/183 (95.1%) | unchanged |
| Decoy | 33/36 (91.7%) | unchanged |
| Compound | 27/30 (90.0%) | unchanged |
| Reorder | 27/30 (90.0%) | unchanged |
| No-good-fit | unscored (15 reps) | top-1 recorded for manual read |
| **OVERALL** | **261/279 (93.5%)** | corrected |

---

## Impact on Verdict

The correction strengthens e4b-mlx's pass result (93.5% vs the original 88.8%). The qualitative verdict from the original report stands: e4b-mlx clears the acceptance bar; e2b-mlx does not.

The `run_bench.py` fix is applied in the same commit as this addendum.
