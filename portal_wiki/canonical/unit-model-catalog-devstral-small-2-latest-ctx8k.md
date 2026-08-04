---
id: unit-model-catalog-devstral-small-2-latest-ctx8k
kind: what
title: "MODEL_CATALOG \u2014 `devstral-small-2:latest-ctx8k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: ba66a30a47f104a137e20da5d5a3e3e9cc0b3360
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6435
updated_at: 1784946220.6435
---

`devstral-small-2:latest-ctx8k` is the 8192-token capped version of `devstral-small-2:latest`. `config/backends.yaml` lists it under the `coding` group with `supports_tools: true` and again under the `security` group with `supports_tools: true`, so both pools treat it as tool-capable. The cap is applied with `portal models apply-params` because the chat-completions endpoint drops request-time context settings; a dedicated tag is the only reliable way to bound the window. `config/portal.yaml` binds the base `devstral-small-2:latest` id to the `bench-devstral-small-2` workspace `model_hint`.

## Why

The dual `coding`/`security` registration in `config/backends.yaml` is what makes this derived id reachable in two pools, and the portal file points its bench workspace at the parent tag rather than this one. Grounding to both files captures that split accurately while the context-cap rationale stays as background context.
