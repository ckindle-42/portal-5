---
id: unit-model-catalog-granite4-1-8b
kind: what
title: "MODEL_CATALOG \u2014 `granite4.1:8b`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: aae69a16de501e8524f279c9bff13f3fdc241f32
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.631973
updated_at: 1784946220.631973
---

`granite4.1:8b` is registered in `config/backends.yaml` under the `general`, `security`, and `reasoning` groups, all with `supports_tools: true`. `config/portal.yaml` uses it widely: the `tools-specialist` workspace `model_hint` is the `granite4.1:8b-ctx8k` variant, the compliance workspace's `tool_model` is `granite4.1:8b-ctx8k`, and the image-generation lane names `granite4.1:8b` as its driver. The `bench-granite41-8b` description cites a dense 8B no-think model (~5.3GB Q4_K_M, Apache 2.0, ISO-certified, BFCL V3 68.3). It replaced `dolphin-llama3:8b` at this fallback position because it is tool-tagged while the Dolphin model is not; `dolphin-llama3:8b` remains registered in the `general` group for `model_hint` continuity.

## Why

The three group registrations in `config/backends.yaml` all assert `supports_tools: true`, which is the mechanical basis for the tool-tagged claim, and `config/portal.yaml` supplies the workspace bindings (tools-specialist, compliance `tool_model`, image driver) plus the BFCL score. The replacement-of-Dolphin history is institutional knowledge explaining why this model holds the tool-capable fallback position.
