---
id: unit-model-catalog-qwen3-6-27b-q8-0
kind: what
title: "MODEL_CATALOG \u2014 `qwen3.6:27b-q8_0`"
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
created_at: 1784946220.633513
updated_at: 1784946220.633513
---

`qwen3.6:27b-q8_0` is the Q8 build of Qwen3.6-27B (~29GB, Alibaba, dense 27B, Apache 2.0), the high-precision quality-lane candidate. `config/backends.yaml` registers it in `group: reasoning` with `supports_tools: true`. `config/portal.yaml`'s `bench-qwen36-27b` workspace names it in its description as the quality candidate and Phase-5 MTP A/B base, though that bench's `model_hint` actually pins the Q4 tag `qwen3.6:27b-q4_K_M`; the Q8 description survives as the bench's stated subject. `bench-qwen36-27b` was re-pointed from the abliterated variant to this stock q8 build.

## Why

Grounding anchors the model to the reasoning-group registration with supports_tools true, and to the bench-qwen36-27b description that names it as the quality candidate. The distinction between the description naming q8_0 and the `model_hint` pinning q4_K_M is the sort of mismatch doc-only prose hides; the unit states both facts as the config carries them.
