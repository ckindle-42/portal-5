---
id: SEC_BENCH-agentic-blue-deltas-20260706
kind: what
title: 'Agentic Blue Arm Deltas: harness contribution (2026-07-06 15:14 UTC)'
sources:
- type: bench-security
  path: /tmp/agentic_blue_sweep.json
last_generated_commit: ''
confidence: high
tags:
- agentic-blue
- maturation
- arm-deltas
- granite4.1-8b-ctx8k
- gpt-oss-20b
- huihui_ai/qwen3.5-abliterated-9b
created_at: 1783350875.3138921
updated_at: 1783350875.3138921
---

# Agentic Blue Eval — Arm-vs-Arm Delta Report

**Trials per cell:** 3  
**Scenarios:** asrep_to_lateral, kerberoast_to_da, meta3_ftp_backdoor  
**Sweep date:** 2026-07-06 15:14 UTC

## Per-Model Arm Deltas (the harness-contribution number)

The three-arm design exists to answer: **does the harness beat raw, for the same model, and by how much?** The delta `harness−raw` is the harness contribution.

### `gpt-oss:20b`

| Tier | raw | tools | harness | harness−raw | harness−tools |
|------|-----|-------|---------|-------------|---------------|
| exact | 0.037 | 0.037 | 0.037 | +0.000 | +0.000 |
| parent | 0.185 | 0.093 | 0.130 | -0.055 RED-FLAG | +0.037 |
| tactic | 0.370 | 0.185 | 0.167 | -0.203 RED-FLAG | -0.018 |

### `granite4.1:8b-ctx8k`

| Tier | raw | tools | harness | harness−raw | harness−tools |
|------|-----|-------|---------|-------------|---------------|
| exact | 0.130 | 0.000 | 0.074 | -0.056 RED-FLAG | +0.074 |
| parent | 0.204 | 0.000 | 0.241 | +0.037 | +0.241 |
| tactic | 0.241 | 0.000 | 0.241 | +0.000 | +0.241 |

### `huihui_ai/qwen3.5-abliterated:9b`

| Tier | raw | tools | harness | harness−raw | harness−tools |
|------|-----|-------|---------|-------------|---------------|
| exact | 0.000 | 0.000 | 0.056 | +0.056 | +0.056 |
| parent | 0.000 | 0.000 | 0.111 | +0.111 | +0.111 |
| tactic | 0.056 | 0.000 | 0.111 | +0.056 | +0.111 |

## RED FLAGS (harness < raw)

These cells show the harness underperforming raw — possible arm-wiring bug or harness regression:

- gpt-oss:20b/parent: harness=0.130 < raw=0.185
- gpt-oss:20b/tactic: harness=0.167 < raw=0.370
- granite4.1:8b-ctx8k/exact: harness=0.074 < raw=0.130

## Recommended Seat Config

**Model:** `granite4.1:8b-ctx8k`  
**Arm:** harness (production config — raw/tools are ablations, never deployed)

| Tier | harness recall | pass@3 |
|------|---------------|---------|
| exact | 0.074 | 2/9 |
| parent | 0.241 | 6/9 |
| tactic | 0.241 | 6/9 |
