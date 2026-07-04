---
id: unit-BENCH_CAPABILITY_V11_FINDINGS-methodology-fixes-applied
kind: why
title: "BENCH_CAPABILITY_V11_FINDINGS \u2014 Methodology fixes applied"
sources:
- type: design
  path: docs/BENCH_CAPABILITY_V11_FINDINGS.md
  section: Methodology fixes applied
last_generated_commit: ''
confidence: high
tags:
- docs
- BENCH_CAPABILITY_V11_FINDINGS
created_at: 1783195000.8266408
updated_at: 1783195000.8266408
---


| V10 Problem | V11 Fix |
|---|---|
| `_strip_think()` missed bare-prose reasoning ("Thinking Process:", "The user wants...") | `extract_final_answer()` strips tagged AND bare-prose reasons preambles, finds first answer boundary |
| `max_tokens=512` truncated reasoning models before answer | Reasoning-aware budgets: 8192 for `emits_reasoning` workspaces, 4096 otherwise |
| Probes scored format, not capability | `format_score` and `capability_score` reported separately |
| Single-shot probes blind to multi-turn agentic loop | Multi-turn agentic loop (C1) with planted error for recovery observation |
| Keyword bingo ("merge_intervals", "bottleneck") | Execution-based: code runs against unit tests; tcpdump parsed structurally; numeric answers checked |
| One prompt per category | 3 prompts per capability + held-out variants |
