---
id: unit-model-catalog-fredrezones55-qwen3-6-35b-a3b-uncensored-hauhaucs-aggressive-q4
kind: what
title: "MODEL_CATALOG \u2014 `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: ba66a30a47f104a137e20da5d5a3e3e9cc0b3360
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.642302
updated_at: 1784946220.642302
---

`fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4` is registered in `config/backends.yaml` under the `creative` group with `supports_tools: true` and under the `general` group with `supports_tools: false` (bench-only intake). `config/portal.yaml` binds it as the `bench-qwen36-hauhaucs` workspace `model_hint` and as the uncensored `pentest` variant `model_hint` of `auto-security`, describing a MoE with 3B active at ~22GB and 0/465 refusals. The HauhauCS abliteration method has the lowest KL-divergence versus the base, vision patched, and robust tool-calling at low quant; an audit-tools run on 2026-06-20 reported a tool_call win that corrected an earlier no-tool result.

## Why

The `creative` group grants `supports_tools: true` while the `general` group keeps it false for bench-only intake — the config fact behind its tool-capable creative role. `config/portal.yaml` supplies the two workspace bindings (`bench-qwen36-hauhaucs` and the pentest variant of `auto-security`) and the institutional zero-refusal and audit-tools notes are preserved as model-card and probe history, respectively.
