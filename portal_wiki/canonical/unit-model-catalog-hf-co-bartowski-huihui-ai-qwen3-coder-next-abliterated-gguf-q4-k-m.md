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
`hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M` was the bartowski GGUF of the huihui-ai abliteration of Qwen3-Coder-Next (80B/3B MoE agentic coder, ~46GB, 74k downloads, Feb 2026) — the no-refusals variant. **RETIRED 2026-10-22 (operator fleet prune): the registration, the `bench-qwen3-coder-next-abliterated` lane, and the `auto-spl` / `uncensored-agentic` pins are removed; those two seats now hint `Huihui-Qwen3.6-27B-abliterated-MLX-4bit`** (see the closeout register, `docs/MODEL_FLEET_CLOSEOUT_20260906.CLOSEOUT.md`). Historical wiring: `config/backends.yaml` had listed it with `supports_tools: true` in every group (verified 2026-09-25 by a neutral native tool-call probe — sibling -ctx64k tag: 3/3 single-call plus a clean tool-result turn); the router reads one flag per model id, last entry wins, so a per-group split never took effect. `config/portal.yaml` had selected the `-ctx64k` derived tag as the `model_hint` for `auto-spl` and for the `uncensored-agentic` variant of `auto-coding`, while the base id was the `model_hint` for `bench-qwen3-coder-next-abliterated`, the head-to-head against the non-abliterated `bench-qwen3-coder-next`.

## Why

The old body asserted `supports_tools=true` without qualification; re-grounding found the flag is group-split in `config/backends.yaml` — false in `general`, true in `coding` — and corrects the claim. `config/portal.yaml` shows the base id routes to the bench lane while the derived tag carries the production `model_hint`s. The tooling claim now reads exactly as the config declares it, with the abliterated-uncensored identity kept as model-card knowledge.
