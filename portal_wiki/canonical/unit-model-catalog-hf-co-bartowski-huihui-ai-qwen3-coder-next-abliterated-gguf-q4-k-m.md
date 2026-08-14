---
id: unit-model-catalog-hf-co-bartowski-huihui-ai-qwen3-coder-next-abliterated-gguf-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.613122
updated_at: 1784946220.613122
---

`hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M` is the bartowski GGUF of the huihui-ai abliteration of Qwen3-Coder-Next (80B/3B MoE agentic coder, ~46GB, 74k downloads, Feb 2026) — the no-refusals variant. `config/backends.yaml` registers it in two groups with a split flag: the `general` group lists `supports_tools: false` (conservative default, not live-probed), while the `coding` group lists `supports_tools: true` per the Qwen coding-family architecture. `config/portal.yaml` selects the `-ctx64k` derived tag as the `model_hint` for `auto-spl` and for the `uncensored-agentic` variant of `auto-coding`, while the base id is the `model_hint` for `bench-qwen3-coder-next-abliterated`, the head-to-head against the non-abliterated `bench-qwen3-coder-next`.

## Why

The old body asserted `supports_tools=true` without qualification; re-grounding found the flag is group-split in `config/backends.yaml` — false in `general`, true in `coding` — and corrects the claim. `config/portal.yaml` shows the base id routes to the bench lane while the derived tag carries the production `model_hint`s. The tooling claim now reads exactly as the config declares it, with the abliterated-uncensored identity kept as model-card knowledge.
