---
id: unit-model-catalog-omnicoder2-9b-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `omnicoder2:9b-q4_k_m`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 925f52c4b7e7ec876ea24823d3a221c7f2f8f505
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.606742
updated_at: 1784946220.606742
---

`omnicoder2:9b-q4_k_m` is OmniCoder-2 9B Q4_K_M (~5.7GB, Apache 2.0), a Qwen3.5-9B base SFT on 425K agentic trajectories from Claude Opus 4.6 / GPT-5.4 / Codex / Gemini 3.1 Pro. `config/backends.yaml` registers it in `group: general` with `supports_tools: false` and in `group: coding` with `supports_tools: true`, so the tool flag is resolved per backend group. `config/portal.yaml` pins it as the `bench-omnicoder2` workspace `model_hint`; the pull registry lists its `ollama_name` from the mradermacher GGUF. The auto-coding uncensored variant instead serves the ctx8k sibling. v2 fixes v1's repetition loops, bloated thinking, and agentic-loop instability.

## Why

The old body asserted supports_tools=false pending audit, but backends.yaml now carries a per-group split: false in `general`, true in `coding`. Grounding to both groups plus the bench workspace and the pull registry corrects that stale claim. The uncensored-variant hint is noted to distinguish the base id from the ctx8k tag it actually serves.
