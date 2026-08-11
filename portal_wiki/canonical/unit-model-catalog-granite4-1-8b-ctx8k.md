---
id: unit-model-catalog-granite4-1-8b-ctx8k
kind: what
title: "MODEL_CATALOG \u2014 `granite4.1:8b-ctx8k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 1ed83b22525c97ed996c835b7519e10c75d13ad0
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.641385
updated_at: 1784946220.641385
---

`granite4.1:8b-ctx8k` is the 8K-context derived tag of `granite4.1:8b`. `config/backends.yaml` lists it in the `general`, `security`, and `reasoning` groups with `supports_tools: true` in each, so the tool-calling capability survives the tighter context bound. `config/portal.yaml` selects it as the `model_hint` for `tools-specialist` — the structured function/API-composition workspace that substitutes for ToolACE-2.5 — and as the blue `tool_model` for the `blueteam-council` and `blueteam-orchestrated` variants of `auto-security`; it is also the `model_hint` for `bench-granite41-8b`. Like every capped tag, `PARAMETER num_ctx 8192` is baked in because Ollama ignores request-time context options; the derived tag is what makes a per-workspace 8K cap reachable.

## Why

Re-grounding anchors this unit to the two config files that actually determine its content: `config/backends.yaml` proves the tag id, its three groups, and the `supports_tools` flags, while `config/portal.yaml` proves where the 8K variant is actually wired (tools-specialist, blueteam tool_model, bench lane). The doc-only provenance is replaced by checkable source paths.
