---
id: SEC_BENCH-agentic-blue-deltas-20260708
kind: what
title: 'Agentic Blue Arm Deltas (with CI): harness contribution (2026-07-08 03:43
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
- hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF-UD-Q4_K_XL
created_at: 1783482239.635063
updated_at: 1783482239.635063
---

# Agentic Blue Eval — Arm-vs-Arm Delta Report (with Confidence Intervals)

**Trials per cell:** 10  
**Scenarios:** 1  
**Sweep date:** 2026-07-08 03:43 UTC

## Per-Model Arm Deltas with 95% Bootstrap CI

The three-arm design exists to answer: **does the harness beat raw, for the same model, and by how much?** Each delta is reported with a 95% bootstrap confidence interval. A delta is only a WIN if its CI excludes 0 on the positive side; a REGRESSION only if the CI excludes 0 on the negative side; otherwise it is INCONCLUSIVE (within noise).

### `hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF:UD-Q4_K_XL`

| Tier | raw | harness | delta | 95% CI | verdict |
|------|-----|---------|-------|--------|---------|
| exact | 0.000 | 0.000 | +0.000 | [+0.000, +0.000] | INCONCLUSIVE |
| parent | 0.000 | 0.000 | +0.000 | [+0.000, +0.000] | INCONCLUSIVE |
| tactic | 0.000 | 0.000 | +0.000 | [+0.000, +0.000] | INCONCLUSIVE |

## Verdict Summary

- All deltas are INCONCLUSIVE — harness effect within noise at current power.

**Inconclusive cells:** 3 — these cannot be declared wins or regressions.

## Recommended Seat Config

**Model:** `hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF:UD-Q4_K_XL`  
**Arm:** harness (production config — raw/tools are ablations, never deployed)

| Tier | harness recall | pass@10 | verdict |
|------|---------------|---------|---------|
| exact | 0.000 | 0/10 | INCONCLUSIVE |
| parent | 0.000 | 0/10 | INCONCLUSIVE |
| tactic | 0.000 | 0/10 | INCONCLUSIVE |
