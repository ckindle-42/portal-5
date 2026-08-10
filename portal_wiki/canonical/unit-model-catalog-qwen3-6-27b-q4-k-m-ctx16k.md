---
id: unit-model-catalog-qwen3-6-27b-q4-k-m-ctx16k
kind: what
title: "MODEL_CATALOG \u2014 `qwen3.6:27b-q4_K_M-ctx16k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 9c0a4efa9fea8836ee3466b206c01b042c59455f
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1785470000
updated_at: 1785470000
---

`qwen3.6:27b-q4_K_M-ctx16k` is the derived tag of `qwen3.6:27b-q4_K_M` with `PARAMETER num_ctx 16384` baked in via the `apply-params` command, created as a P5-ROUTER-EVICTION-001 follow-up. `config/backends.yaml` registers it in `group: general` with `supports_tools: false`. `config/portal.yaml` pins it as the `auto-council` workspace `model_hint` with `context_limit: 16384` and uses it as the council `synthesizer_model`. Because the base's native 262144-token context would reserve enormous KV cache and evict the fleet, the council lane needed a dedicated capped id rather than a request-time option the endpoint ignores.

## Why

Grounding anchors the tag to the general-group registration and to the auto-council wiring in portal.yaml — the `model_hint`, the matching `context_limit`, and the `synthesizer_model` role. The eviction rationale is kept because it is the institutional reason this derived id exists at all; the tag is not a parity artifact but the fix for a specific routing problem.
