---
id: SEC_BENCH-agentic-blue-winning-20260706
kind: what
title: 'CORRECTED — was misleading: "granite (raw)" was a selection artifact'
sources:
- type: bench-security
  path: /tmp/agentic_blue_sweep.json
last_generated_commit: ''
confidence: high
tags:
- agentic-blue
- maturation
- corrected
- superseded
created_at: 1783347779.178504
updated_at: 1783351200.0
---

# CORRECTED — Superseded by SEC_BENCH-agentic-blue-deltas-20260706

**This unit was misleading.** It reported "winning config: granite (raw)" by selecting the single
best (model, arm) cell regardless of arm. This was a **selection artifact**, not a finding — raw/tools
are ablations to measure harness contribution, never the deployed config. The three-arm design exists to
answer "does harness beat raw, for the same model, by how much?" — this unit obscured that question.

**See: `SEC_BENCH-agentic-blue-deltas-20260706`** for the corrected arm-vs-arm delta report.

## What the corrected data shows

Per the delta report (averaged across 3 scenarios, 3 trials):

| Model | Tier | raw | harness | harness−raw |
|-------|------|-----|---------|-------------|
| granite | exact | 0.130 | 0.074 | −0.056 RED-FLAG |
| granite | parent | 0.204 | 0.241 | +0.037 |
| granite | tactic | 0.241 | 0.241 | +0.000 |
| qwen3.5 | exact | 0.000 | 0.056 | +0.056 |
| qwen3.5 | parent | 0.000 | 0.111 | +0.111 |

- **Harness beats raw on granite at parent tier** (+0.037) — the tier that matters for sub-technique precision.
- Granite exact shows RED-FLAG (harness < raw) — possible regression to investigate.
- **qwen3.5 harness clearly beats raw** across all tiers — harness contribution positive.
- The recommended seat config is granite (harness arm), not granite (raw).
