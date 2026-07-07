---
id: SEC_BENCH-agentic-blue-deltas-20260707
kind: what
title: 'Agentic Blue Arm Deltas (with CI): harness contribution (2026-07-07 01:09
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
- gpt-oss-20b
- huihui_ai/qwen3.5-abliterated-9b
created_at: 1783386564.2440681
updated_at: 1783386564.2440681
---

# Agentic Blue Eval — Arm-vs-Arm Delta Report (with Confidence Intervals)

**Trials per cell:** 3  
**Scenarios:** 1  
**Sweep date:** 2026-07-07 01:09 UTC

## Per-Model Arm Deltas with 95% Bootstrap CI

The three-arm design exists to answer: **does the harness beat raw, for the same model, and by how much?** Each delta is reported with a 95% bootstrap confidence interval. A delta is only a WIN if its CI excludes 0 on the positive side; a REGRESSION only if the CI excludes 0 on the negative side; otherwise it is INCONCLUSIVE (within noise).

### `gpt-oss:20b`

| Tier | raw | harness | delta | 95% CI | verdict |
|------|-----|---------|-------|--------|---------|
| exact | 0.000 | 0.000 | +0.000 | [+0.000, +0.000] | INCONCLUSIVE |
| parent | 0.111 | 0.000 | -0.111 | [-0.111, -0.111] | SIGNIFICANT-REGRESSION |
| tactic | 0.778 | 0.000 | -0.778 | [-0.778, -0.778] | SIGNIFICANT-REGRESSION |

### `granite4.1:8b-ctx8k`

| Tier | raw | harness | delta | 95% CI | verdict |
|------|-----|---------|-------|--------|---------|
| exact | 0.111 | 0.333 | +0.222 | [+0.222, +0.222] | SIGNIFICANT-WIN |
| parent | 0.222 | 0.333 | +0.111 | [+0.111, +0.111] | SIGNIFICANT-WIN |
| tactic | 0.444 | 0.333 | -0.111 | [-0.111, -0.111] | SIGNIFICANT-REGRESSION |

### `huihui_ai/qwen3.5-abliterated:9b`

| Tier | raw | harness | delta | 95% CI | verdict |
|------|-----|---------|-------|--------|---------|
| exact | 0.000 | 0.000 | +0.000 | [+0.000, +0.000] | INCONCLUSIVE |
| parent | 0.000 | 0.000 | +0.000 | [+0.000, +0.000] | INCONCLUSIVE |
| tactic | 0.000 | 0.000 | +0.000 | [+0.000, +0.000] | INCONCLUSIVE |

## Verdict Summary

- **gpt-oss:20b/parent: SIGNIFICANT-REGRESSION** — delta=-0.111, CI=[-0.111, -0.111]
- **gpt-oss:20b/tactic: SIGNIFICANT-REGRESSION** — delta=-0.778, CI=[-0.778, -0.778]
- **granite4.1:8b-ctx8k/exact: SIGNIFICANT-WIN** — delta=+0.222, CI=[+0.222, +0.222]
- **granite4.1:8b-ctx8k/parent: SIGNIFICANT-WIN** — delta=+0.111, CI=[+0.111, +0.111]
- **granite4.1:8b-ctx8k/tactic: SIGNIFICANT-REGRESSION** — delta=-0.111, CI=[-0.111, -0.111]

**Inconclusive cells:** 4 — these cannot be declared wins or regressions.

## Recommended Seat Config

**Model:** `granite4.1:8b-ctx8k`  
**Arm:** harness (production config — raw/tools are ablations, never deployed)

| Tier | harness recall | pass@3 | verdict |
|------|---------------|---------|---------|
| exact | 0.333 | 3/3 | SIGNIFICANT-WIN |
| parent | 0.333 | 3/3 | SIGNIFICANT-WIN |
| tactic | 0.333 | 3/3 | SIGNIFICANT-REGRESSION |
