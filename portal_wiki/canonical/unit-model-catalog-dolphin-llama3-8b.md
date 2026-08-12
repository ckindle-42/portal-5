---
id: unit-model-catalog-dolphin-llama3-8b
kind: what
title: "MODEL_CATALOG \u2014 `dolphin-llama3:8b`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: 640a004e4a83811639544dfada51fcd1268b0688
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.640996
updated_at: 1784946220.640996
---

`dolphin-llama3:8b` is registered in `config/backends.yaml` under the `general` group and the `creative` group, both with `supports_tools: false`. It is an uncensored, creative-tuned model dispatched only through the Path 2 (OWUI MCP) route; the pipeline never attaches tools to `auto-creative` requests, consistent with the tool-negative flags on both registrations.

## Why

Both registrations of `dolphin-llama3:8b` in `config/backends.yaml` carry `supports_tools: false`, which is the mechanical basis for the claim that the pipeline never attaches tools to creative requests. The unit is grounded to the backend file alone because `config/portal.yaml` does not reference the id as a workspace `model_hint`, so the config source is the backend registry.
