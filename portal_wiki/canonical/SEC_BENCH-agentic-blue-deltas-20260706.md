---
id: SEC_BENCH-agentic-blue-deltas-20260706
kind: what
title: 'Agentic Blue Arm Deltas (with CI): harness contribution (2026-07-06 16:52
  UTC)'
sources:
- type: bench-security
  path: /tmp/agentic_blue_sweep.json
last_generated_commit: ''
confidence: high
tags:
- agentic-blue
- maturation
- arm-deltas
- confidence-interval
- granite4.1-8b-ctx8k
created_at: 1783356754.65727
updated_at: 1783356754.65727
---

# Agentic Blue Eval — Arm-vs-Arm Delta Report (with Confidence Intervals)

**Trials per cell:** 1  
**Scenarios:** 1  
**Sweep date:** 2026-07-06 16:52 UTC

## Per-Model Arm Deltas with 95% Bootstrap CI

The three-arm design exists to answer: **does the harness beat raw, for the same model, and by how much?** Each delta is reported with a 95% bootstrap confidence interval. A delta is only a WIN if its CI excludes 0 on the positive side; a REGRESSION only if the CI excludes 0 on the negative side; otherwise it is INCONCLUSIVE (within noise).

### `granite4.1:8b-ctx8k`

| Tier | raw | harness | delta | 95% CI | verdict |
|------|-----|---------|-------|--------|---------|
| exact | 0.000 | 0.000 | +0.000 | [+0.000, +0.000] | INCONCLUSIVE |
| parent | 0.000 | 0.000 | +0.000 | [+0.000, +0.000] | INCONCLUSIVE |
| tactic | 0.333 | 0.000 | -0.333 | [-0.333, -0.333] | SIGNIFICANT-REGRESSION |

## Verdict Summary

- **granite4.1:8b-ctx8k/tactic: SIGNIFICANT-REGRESSION** — delta=-0.333, CI=[-0.333, -0.333]

**Inconclusive cells:** 2 — these cannot be declared wins or regressions.

## Recommended Seat Config

**Model:** `granite4.1:8b-ctx8k`  
**Arm:** harness (production config — raw/tools are ablations, never deployed)

| Tier | harness recall | pass@1 | verdict |
|------|---------------|---------|---------|
| exact | 0.000 | 0/1 | INCONCLUSIVE |
| parent | 0.000 | 0/1 | INCONCLUSIVE |
| tactic | 0.000 | 0/1 | SIGNIFICANT-REGRESSION |
