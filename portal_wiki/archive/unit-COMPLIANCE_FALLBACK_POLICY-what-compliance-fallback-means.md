---
id: unit-COMPLIANCE_FALLBACK_POLICY-what-compliance-fallback-means
historical: true
kind: why
title: "COMPLIANCE_FALLBACK_POLICY \u2014 What \"compliance fallback\" means"
sources:
- type: design
  path: docs/COMPLIANCE_FALLBACK_POLICY.md
  section: What "compliance fallback" means
confidence: high
tags:
- docs
- COMPLIANCE_FALLBACK_POLICY

---


The `auto-compliance` workspace routes through `[reasoning, general]`
groups in that priority order. The primary model hint is `granite4.1:8b`
(IBM Granite 4.1 8B, Ollama GGUF, BFCL V3 #1 structured output, Apache 2.0).
When `granite4.1:8b` is evicted or under memory pressure, the pipeline
falls through to other Ollama models in the reasoning and general groups.

Note: the MLX inference proxy was retired at commit 75c24a9 — the former
`[mlx, reasoning, general]` group priority and the MLX primary
(`Jackrong/MLX-Qwen3.5-35B-A3B-Claude-...-8bit`) no longer apply.

Every Ollama model in `ollama-reasoning` and `ollama-general` is
therefore a potential primary handler for a compliance request. This
policy specifies the bar each must meet to remain in those groups.
