---
id: unit-model-catalog-granite4-1-30b-ctx16k
kind: what
title: "MODEL_CATALOG \u2014 `granite4.1:30b-ctx16k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 50b73876729db7181402fcbcc48400caa1ba1e40
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1785465745
updated_at: 1785465745
---

`granite4.1:30b-ctx16k` is the 16384-token bounded form of `granite4.1:30b`. `config/backends.yaml` registers it under the `reasoning` group with `supports_tools: true` and under the `general` group with `supports_tools: false`. `config/portal.yaml` uses it in three places: the `bench-granite41-30b` workspace `model_hint`, the compliance workspace's `reasoning_model`, and the Evidence Auditor member model of the council workspace. The bound is baked in via `portal models apply-params` because the completion API ignores request-time context settings.

## Why

This derived id is unusual in that three `config/portal.yaml` bindings consume it, which is why the portal file matters as much as the `reasoning`/`general` registrations in `config/backends.yaml`. The multi-workspace usage and the group split together justify citing both config sources for the 16K variant.
