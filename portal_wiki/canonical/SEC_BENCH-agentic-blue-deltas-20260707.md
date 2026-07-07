---
id: SEC_BENCH-agentic-blue-deltas-20260707
kind: what
title: 'Agentic Blue Arm Deltas (with CI): harness contribution (2026-07-07 14:51
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
created_at: 1783435909.6864178
updated_at: 1783435909.6864178
---

# Agentic Blue Eval — Arm-vs-Arm Delta Report (with Confidence Intervals)

**Trials per cell:** 10  
**Scenarios:** 88  
**Sweep date:** 2026-07-07 14:51 UTC

## Per-Model Arm Deltas with 95% Bootstrap CI

The three-arm design exists to answer: **does the harness beat raw, for the same model, and by how much?** Each delta is reported with a 95% bootstrap confidence interval. A delta is only a WIN if its CI excludes 0 on the positive side; a REGRESSION only if the CI excludes 0 on the negative side; otherwise it is INCONCLUSIVE (within noise).

### `granite4.1:8b-ctx8k`

| Tier | raw | harness | delta | 95% CI | verdict |
|------|-----|---------|-------|--------|---------|
| exact | 0.221 | 0.126 | -0.094 | [-0.124, -0.066] | SIGNIFICANT-REGRESSION |
| parent | 0.263 | 0.139 | -0.124 | [-0.154, -0.095] | SIGNIFICANT-REGRESSION |
| tactic | 0.325 | 0.157 | -0.169 | [-0.205, -0.134] | SIGNIFICANT-REGRESSION |

## Verdict Summary

- **granite4.1:8b-ctx8k/exact: SIGNIFICANT-REGRESSION** — delta=-0.094, CI=[-0.124, -0.066]
- **granite4.1:8b-ctx8k/parent: SIGNIFICANT-REGRESSION** — delta=-0.124, CI=[-0.154, -0.095]
- **granite4.1:8b-ctx8k/tactic: SIGNIFICANT-REGRESSION** — delta=-0.169, CI=[-0.205, -0.134]

**Inconclusive cells:** 0 — these cannot be declared wins or regressions.

## Recommended Seat Config

**Model:** `granite4.1:8b-ctx8k`  
**Arm:** harness (production config — raw/tools are ablations, never deployed)

| Tier | harness recall | pass@10 | verdict |
|------|---------------|---------|---------|
| exact | 0.126 | 187/880 | SIGNIFICANT-REGRESSION |
| parent | 0.139 | 217/880 | SIGNIFICANT-REGRESSION |
| tactic | 0.157 | 248/880 | SIGNIFICANT-REGRESSION |
