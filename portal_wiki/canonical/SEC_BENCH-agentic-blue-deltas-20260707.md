---
id: SEC_BENCH-agentic-blue-deltas-20260707
kind: what
title: 'Agentic Blue Arm Deltas (with CI): harness contribution (2026-07-07 15:36
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
created_at: 1783438581.206892
updated_at: 1783438581.206892
---

# Agentic Blue Eval — Arm-vs-Arm Delta Report (with Confidence Intervals)

**Trials per cell:** 1  
**Scenarios:** 4  
**Sweep date:** 2026-07-07 15:36 UTC

## Per-Model Arm Deltas with 95% Bootstrap CI

The three-arm design exists to answer: **does the harness beat raw, for the same model, and by how much?** Each delta is reported with a 95% bootstrap confidence interval. A delta is only a WIN if its CI excludes 0 on the positive side; a REGRESSION only if the CI excludes 0 on the negative side; otherwise it is INCONCLUSIVE (within noise).

### `granite4.1:8b-ctx8k`

| Tier | raw | harness | delta | 95% CI | verdict |
|------|-----|---------|-------|--------|---------|
| exact | 0.000 | 0.083 | +0.083 | [+0.333, +0.333] | SIGNIFICANT-WIN |
| parent | 0.000 | 0.167 | +0.167 | [+0.333, +0.333] | SIGNIFICANT-WIN |
| tactic | 0.000 | 0.167 | +0.167 | [+0.333, +0.333] | SIGNIFICANT-WIN |

## Verdict Summary

- **granite4.1:8b-ctx8k/exact: SIGNIFICANT-WIN** — delta=+0.083, CI=[+0.333, +0.333]
- **granite4.1:8b-ctx8k/parent: SIGNIFICANT-WIN** — delta=+0.167, CI=[+0.333, +0.333]
- **granite4.1:8b-ctx8k/tactic: SIGNIFICANT-WIN** — delta=+0.167, CI=[+0.333, +0.333]

**Inconclusive cells:** 0 — these cannot be declared wins or regressions.

## Recommended Seat Config

**Model:** `granite4.1:8b-ctx8k`  
**Arm:** harness (production config — raw/tools are ablations, never deployed)

| Tier | harness recall | pass@1 | verdict |
|------|---------------|---------|---------|
| exact | 0.083 | 1/4 | SIGNIFICANT-WIN |
| parent | 0.167 | 2/4 | SIGNIFICANT-WIN |
| tactic | 0.167 | 2/4 | SIGNIFICANT-WIN |
