---
id: SEC_BENCH-agentic-blue-deltas-20260708
kind: what
title: 'Agentic Blue Arm Deltas (with CI): harness contribution (2026-07-08 11:56
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
- devstral-small-2-latest-ctx8k
- granite4.1-8b-ctx8k
created_at: 1783511802.0104551
updated_at: 1783511802.0104551
---

# Agentic Blue Eval — Arm-vs-Arm Delta Report (with Confidence Intervals)

**Trials per cell:** 10  
**Scenarios:** 20  
**Sweep date:** 2026-07-08 11:56 UTC

## Per-Model Arm Deltas with 95% Bootstrap CI

The three-arm design exists to answer: **does the harness beat raw, for the same model, and by how much?** Each delta is reported with a 95% bootstrap confidence interval. A delta is only a WIN if its CI excludes 0 on the positive side; a REGRESSION only if the CI excludes 0 on the negative side; otherwise it is INCONCLUSIVE (within noise).

### `devstral-small-2:latest-ctx8k`

| Tier | raw | harness | delta | 95% CI | verdict |
|------|-----|---------|-------|--------|---------|
| exact | 0.172 | 0.078 | -0.093 | [-0.196, +0.036] | INCONCLUSIVE |
| parent | 0.334 | 0.082 | -0.252 | [-0.391, -0.091] | SIGNIFICANT-REGRESSION |
| tactic | 0.421 | 0.085 | -0.337 | [-0.483, -0.161] | SIGNIFICANT-REGRESSION |

### `granite4.1:8b-ctx8k`

| Tier | raw | harness | delta | 95% CI | verdict |
|------|-----|---------|-------|--------|---------|
| exact | 0.052 | 0.121 | +0.069 | [+0.000, +0.167] | SIGNIFICANT-WIN |
| parent | 0.133 | 0.142 | +0.009 | [-0.069, +0.111] | INCONCLUSIVE |
| tactic | 0.200 | 0.156 | -0.044 | [-0.131, +0.070] | INCONCLUSIVE |

## Verdict Summary

- **devstral-small-2:latest-ctx8k/parent: SIGNIFICANT-REGRESSION** — delta=-0.252, CI=[-0.391, -0.091]
- **devstral-small-2:latest-ctx8k/tactic: SIGNIFICANT-REGRESSION** — delta=-0.337, CI=[-0.483, -0.161]
- **granite4.1:8b-ctx8k/exact: SIGNIFICANT-WIN** — delta=+0.069, CI=[+0.000, +0.167]

**Inconclusive cells:** 3 — these cannot be declared wins or regressions.

## Recommended Seat Config

**Model:** `granite4.1:8b-ctx8k`  
**Arm:** harness (production config — raw/tools are ablations, never deployed)

| Tier | harness recall | pass@10 | verdict |
|------|---------------|---------|---------|
| exact | 0.121 | 46/200 | SIGNIFICANT-WIN |
| parent | 0.142 | 56/200 | INCONCLUSIVE |
| tactic | 0.156 | 64/200 | INCONCLUSIVE |
