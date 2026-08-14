---
id: unit-model-catalog-hf-co-bartowski-nvidia-nemotron-3-5-lightning-30b-a3b-gguf-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: 41df61e0a6102275a700700e9765972f1508c4c5
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1786736000.0
updated_at: 1786736000.0
---

`hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M` is the Q4_K_M GGUF quant of NVIDIA's Nemotron 3.5 Lightning 30B-A3B MoE model, served by Ollama. Added 2026-08-14 as the fallback tier for the new `auto-nemotron` workspace (`config/portal.yaml`), pinned as its `model_hint`. `config/backends.yaml` registers it in `ollama-general` (group `general`) with `supports_tools: true`, live-audited via a direct `/api/chat` tool-call probe (clean `tool_calls`, correctly typed arguments). The `omlx-general` entry's `aliases` block maps this hint onto `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp` (see that unit), so oMLX serves the workspace by default at `priority: 10` with this GGUF as the automatic fallback when oMLX is unhealthy. Measured standalone on Ollama: 52.9-53.1 tok/s steady-state, versus 70.0-70.3 tok/s on the oMLX+MTP path — kept as the production fallback deliberately, matching the dual-backend pattern used across every other oMLX-shadowed group in this fleet, rather than going oMLX-only given oMLX is running a dev prerelease (0.6.0.dev1) for this rollout.

## Why

Grounding anchors the model to its role as the auto-nemotron workspace's fallback tier and to the alias that lets oMLX serve the same hint at higher priority. The measured tok/s gap between this GGUF path and the oMLX+MTP path is kept as a measured result, and the rationale for keeping the fallback (dev-prerelease oMLX, established dual-backend convention) is recorded rather than left implicit.
