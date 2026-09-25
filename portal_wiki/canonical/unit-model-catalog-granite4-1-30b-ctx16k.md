---
id: unit-model-catalog-granite4-1-30b-ctx16k
kind: what
title: "MODEL_CATALOG \u2014 `granite4.1:30b-ctx16k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1785465745
updated_at: 1785465745
---
`granite4.1:30b-ctx16k` is the 16384-token bounded form of `granite4.1:30b`. `config/backends.yaml` lists it with `supports_tools: true` in every group (verified 2026-09-25 by a neutral native tool-call probe — 3/3 single-call plus a clean tool-result turn); the router reads one flag per model id, last entry wins, so a per-group split never took effect. `config/portal.yaml` uses it in three places: the `bench-granite41-30b` workspace `model_hint`, the compliance workspace's `reasoning_model`, and the Evidence Auditor member model of the council workspace. The bound is baked in via `portal models apply-params` because the completion API ignores request-time context settings.

## Why

This derived id is unusual in that three `config/portal.yaml` bindings consume it, which is why the portal file matters as much as the `reasoning`/`general` registrations in `config/backends.yaml`. The multi-workspace usage and the group split together justify citing both config sources for the 16K variant.
