---
id: unit-model-catalog-baronllm-q6-k
kind: what
title: "MODEL_CATALOG \u2014 `baronllm:q6_k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 86e6f142c0069ca2d4824b4721a545e64bd585b3
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6283011
updated_at: 1784946220.6283011
---

`baronllm:q6_k` is the GATE-D Expert-role candidate (added 2026-07-21, user-requested) — the non-abliterated original BaronLLM (Llama-3.1-8B, 53K cybersec examples, 200+ domains), pulled from the gated `AlicanKiraz0` repo via the `huggingface_hub.hf_hub_download` workaround documented in `config/portal.yaml`'s model pull registry. It is a distinct checkpoint from `huihui_ai/baronllm-abliterated:latest` (different weights, not abliterated); that fork's tool-call reliability finding (`valid_rate 0.25`, dropped from `auto-security`) does not automatically carry over because the Hunter/Expert path runs with tools disabled and reasons over supplied telemetry, which is this model's job rather than MCP tool-calling. In `config/backends.yaml` it is registered under the `security` backend group with `supports_tools: false`, and `config/portal.yaml` gives it the `bench-baronllm-q6k` workspace `model_hint`. Sampling uses temperature 0.6, top_p 0.9, repeat_penalty 1.1, and the chat template reuses `huihui_ai/baronllm-abliterated`'s known-good Llama-3.1 template via `ollama show --modelfile`.

## Why

The model id, its `security` group placement, and its `supports_tools: false` flag are all asserted by `config/backends.yaml`, while `config/portal.yaml` supplies the gated source mapping and the `bench-baronllm-q6k` workspace binding. The institutional knowledge — the distinct-checkpoint caveat against the abliterated fork and the reasoning-role sampling convention — is kept because it explains why a tool-negative registration is intentional for a security reasoning model.
