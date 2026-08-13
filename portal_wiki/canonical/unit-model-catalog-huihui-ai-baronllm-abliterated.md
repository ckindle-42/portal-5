---
id: unit-model-catalog-huihui-ai-baronllm-abliterated
kind: what
title: "MODEL_CATALOG \u2014 `huihui_ai/baronllm-abliterated`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 75c5054f791636f367b62a1776bcc9f631794766
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.641821
updated_at: 1784946220.641821
---

`huihui_ai/baronllm-abliterated` is the no-restrictions creative BaronLLM fork, a Llama-3.1-8B-lineage abliteration trained on 53K cybersec examples across 200+ domains. `config/backends.yaml` registers it under both the `security` and `creative` groups with `supports_tools: true`. `config/portal.yaml` uses it as the lineage behind the `auto-security` uncensored variant (which routes the `:latest-ctx8k` tag) and documents in the `bench-baronllm-q6k` and `bench-qwable-35b` descriptions that it was dropped from auto-security in 2026-07-16 for tool-call unreliability at valid_rate 0.25 — a finding scoped to MCP tool-calling, not the no-tools reasoning path. Tool-calling was originally confirmed via the corrected template.

## Why

The `security` and `creative` dual registration with `supports_tools: true` is asserted directly by `config/backends.yaml`, and `config/portal.yaml` supplies the drop-from-auto-security correction plus the uncensored-variant lineage. The institutional knowledge about the reliability-gate finding is preserved because the portal descriptions are exactly where that reversal is recorded, and it reconciles the true flag with the withdrawal.
