---
id: SEC_BENCH-agentic-blue-deltas-20260707
kind: what
title: 'Agentic Blue Arm Deltas (with CI): harness contribution (2026-07-07 21:58
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
- cybersecqwen-4b-toolfix-latest
- hf.co/mradermacher/VulnLLM-R-7B-GGUF-Q4_K_M
- lfm2.5-8b
- gemma4-12b-it-qat-ctx8k
- gemma4-26b-a4b-it-qat-ctx8k
- devstral-small-2-latest-ctx8k
- gemma4-31b-it-qat-ctx8k
- qwen3-coder-30b-a3b-q4_K_M-ctx8k
created_at: 1783461538.401804
updated_at: 1783461538.401804
---

# Agentic Blue Eval — Arm-vs-Arm Delta Report (with Confidence Intervals)

**Trials per cell:** 3  
**Scenarios:** 3  
**Sweep date:** 2026-07-07 21:58 UTC

## Per-Model Arm Deltas with 95% Bootstrap CI

The three-arm design exists to answer: **does the harness beat raw, for the same model, and by how much?** Each delta is reported with a 95% bootstrap confidence interval. A delta is only a WIN if its CI excludes 0 on the positive side; a REGRESSION only if the CI excludes 0 on the negative side; otherwise it is INCONCLUSIVE (within noise).

### `cybersecqwen-4b-toolfix:latest`

| Tier | raw | harness | delta | 95% CI | verdict |
|------|-----|---------|-------|--------|---------|
| exact | 0.056 | 0.000 | -0.056 | [-0.167, +0.000] | INCONCLUSIVE |
| parent | 0.056 | 0.000 | -0.056 | [-0.167, +0.000] | INCONCLUSIVE |
| tactic | 0.056 | 0.000 | -0.056 | [-0.167, +0.000] | INCONCLUSIVE |

### `devstral-small-2:latest-ctx8k`

| Tier | raw | harness | delta | 95% CI | verdict |
|------|-----|---------|-------|--------|---------|
| exact | 0.093 | 0.333 | +0.241 | [-0.167, +1.000] | INCONCLUSIVE |
| parent | 0.222 | 0.333 | +0.111 | [-0.333, +1.000] | INCONCLUSIVE |
| tactic | 0.333 | 0.333 | +0.000 | [-0.667, +1.000] | INCONCLUSIVE |

### `gemma4:12b-it-qat-ctx8k`

| Tier | raw | harness | delta | 95% CI | verdict |
|------|-----|---------|-------|--------|---------|
| exact | 0.000 | 0.056 | +0.056 | [+0.000, +0.167] | INCONCLUSIVE |
| parent | 0.000 | 0.056 | +0.056 | [+0.000, +0.167] | INCONCLUSIVE |
| tactic | 0.111 | 0.056 | -0.055 | [-0.333, +0.167] | INCONCLUSIVE |

### `gemma4:26b-a4b-it-qat-ctx8k`

| Tier | raw | harness | delta | 95% CI | verdict |
|------|-----|---------|-------|--------|---------|
| exact | 0.111 | 0.000 | -0.111 | [-0.333, +0.000] | INCONCLUSIVE |
| parent | 0.111 | 0.000 | -0.111 | [-0.333, +0.000] | INCONCLUSIVE |
| tactic | 0.148 | 0.000 | -0.148 | [-0.333, +0.000] | INCONCLUSIVE |

### `gemma4:31b-it-qat-ctx8k`

| Tier | raw | harness | delta | 95% CI | verdict |
|------|-----|---------|-------|--------|---------|
| exact | 0.111 | 0.111 | +0.000 | [-0.333, +0.333] | INCONCLUSIVE |
| parent | 0.111 | 0.111 | +0.000 | [-0.333, +0.333] | INCONCLUSIVE |
| tactic | 0.222 | 0.111 | -0.111 | [-0.333, +0.333] | INCONCLUSIVE |

### `hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M`

| Tier | raw | harness | delta | 95% CI | verdict |
|------|-----|---------|-------|--------|---------|
| exact | 0.000 | 0.000 | +0.000 | [+0.000, +0.000] | INCONCLUSIVE |
| parent | 0.000 | 0.000 | +0.000 | [+0.000, +0.000] | INCONCLUSIVE |
| tactic | 0.000 | 0.000 | +0.000 | [+0.000, +0.000] | INCONCLUSIVE |

### `lfm2.5:8b`

| Tier | raw | harness | delta | 95% CI | verdict |
|------|-----|---------|-------|--------|---------|
| exact | 0.000 | 0.074 | +0.074 | [+0.000, +0.222] | INCONCLUSIVE |
| parent | 0.093 | 0.111 | +0.018 | [-0.167, +0.222] | INCONCLUSIVE |
| tactic | 0.130 | 0.111 | -0.019 | [-0.167, +0.111] | INCONCLUSIVE |

### `qwen3-coder:30b-a3b-q4_K_M-ctx8k`

| Tier | raw | harness | delta | 95% CI | verdict |
|------|-----|---------|-------|--------|---------|
| exact | 0.000 | 0.111 | +0.111 | [+0.000, +0.333] | INCONCLUSIVE |
| parent | 0.167 | 0.111 | -0.056 | [-0.333, +0.333] | INCONCLUSIVE |
| tactic | 0.278 | 0.148 | -0.130 | [-0.556, +0.333] | INCONCLUSIVE |

## Verdict Summary

- All deltas are INCONCLUSIVE — harness effect within noise at current power.

**Inconclusive cells:** 24 — these cannot be declared wins or regressions.

## Recommended Seat Config

**Model:** `devstral-small-2:latest-ctx8k`  
**Arm:** harness (production config — raw/tools are ablations, never deployed)

| Tier | harness recall | pass@3 | verdict |
|------|---------------|---------|---------|
| exact | 0.333 | 3/9 | INCONCLUSIVE |
| parent | 0.333 | 3/9 | INCONCLUSIVE |
| tactic | 0.333 | 3/9 | INCONCLUSIVE |
