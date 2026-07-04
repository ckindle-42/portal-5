---
id: unit-BENCH_CAPABILITY_V11_FINDINGS-c3-environment-simulation-3-prompts-seq-ls-df
kind: why
title: "BENCH_CAPABILITY_V11_FINDINGS \u2014 C3 \u2014 Environment Simulation (3 prompts:\
  \ seq, ls, df)"
sources:
- type: design
  path: docs/BENCH_CAPABILITY_V11_FINDINGS.md
  section: "C3 \u2014 Environment Simulation (3 prompts: seq, ls, df)"
last_generated_commit: ''
confidence: high
tags:
- docs
- BENCH_CAPABILITY_V11_FINDINGS
created_at: 1783195000.826889
updated_at: 1783195000.826889
---


| Workspace | format_score | capability_score |
|---|---|---|
| bench-laguna (production IDE default) | 1.00 | **1.00** |
| bench-qwen3-coder-30b (production coder) | 1.00 | 0.67 |
| bench-agentworld | 1.00 | 0.33 |

**Call: REAL capability gap.** AgentWorld trails both baseline models on envsim. With reasoning preambles stripped and fair token budgets, AgentWorld correctly formatted its answers (format=1.00) but the actual simulated outputs were less accurate than laguna's (cap=1.00) and qwen3-coder's (cap=0.67). The V10 hypothesis that "reasoning preamble caused the low score" is NOT the full story — even with the fixed harness, AgentWorld underperforms on this capability.
