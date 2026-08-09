---
id: unit-model-catalog-qwen3-6-27b-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `qwen3.6:27b-q4_K_M`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 63cbca4c591d2d00f1cc9e3101ffa91f84a9a4a0
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6100218
updated_at: 1784946220.6100218
---

`qwen3.6:27b-q4_K_M` is the dense Qwen3.6-27B Q4 build (~16GB, Alibaba, April 2026, Apache 2.0, 262K ctx, 77.2% SWE-bench Verified). `config/backends.yaml` registers it in `group: general` with `supports_tools: false` and in `group: coding` with `supports_tools: true`. `config/portal.yaml` uses it as the IR-playbook hop in the purpleteam-deep and purpleteam-exec chains, as a council member in the auto-security blue variant, and as the `model_hint` of `bench-qwen36-27b` and `bench-qwen36-27b-ud`. Earlier auto-spl/auto-data promotion prose no longer matches portal.yaml, whose hints there point at other models.

## Why

Grounding anchors the model to its two backends.yaml group registrations with their differing supports_tools flags, and to the portal.yaml placements that actually consume it — the purpleteam IR hop, the security council, and the two bench workspaces. The old promotion claim is corrected because portal.yaml's auto-spl and auto-data `model_hint` values no longer reference this id; only the chain, council, and bench wiring is verifiable.
