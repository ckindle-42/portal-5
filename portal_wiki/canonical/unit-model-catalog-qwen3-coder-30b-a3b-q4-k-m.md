---
id: unit-model-catalog-qwen3-coder-30b-a3b-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `qwen3-coder:30b-a3b-q4_K_M`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 640a004e4a83811639544dfada51fcd1268b0688
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.609118
updated_at: 1784946220.609118
---

`qwen3-coder:30b-a3b-q4_K_M` is the Qwen3-Coder 30B-A3B MoE Q4 build (~19GB, Alibaba). `config/backends.yaml` registers it in `group: general` with `supports_tools: false` and in `group: coding` with `supports_tools: true`. `config/portal.yaml` uses it as the DETECTION ENGINEERING hop in the purpleteam-deep and purpleteam-exec chains, and as the `model_hint` of the `bench-qwen3-coder-30b` workspace; the auto-coding and auto-cad descriptions reference the 30B-A3B family. The old auto-spl-primary label is stale — portal.yaml's auto-spl `model_hint` now points at the abliterated coder-next build; this id's live wiring is the chains, the bench, and the coding descriptions.

## Why

Grounding anchors the model to its two backends.yaml registrations with their per-group supports_tools split, and to the portal.yaml placements that consume it — the purpleteam DETECT hop, the bench workspace, and the auto-coding/auto-cad descriptions. The stale auto-spl-primary claim is corrected because portal.yaml's auto-spl `model_hint` no longer references this id; the chain and bench wiring is what the config verifies.
