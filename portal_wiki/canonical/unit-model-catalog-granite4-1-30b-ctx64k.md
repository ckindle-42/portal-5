---
id: unit-model-catalog-granite4-1-30b-ctx64k
kind: what
title: "MODEL_CATALOG \u2014 `granite4.1:30b-ctx64k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: fb9979b75eb4d70f331e849b80fc7326e8e61847
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6461928
updated_at: 1784946220.6461928
---

`granite4.1:30b-ctx64k` is the long-context variant of `granite4.1:30b` with a 65536-token window. `config/backends.yaml` lists it under the `reasoning` group with `supports_tools: true`; unlike the ctx16k sibling it does not appear in the `general` group. `config/portal.yaml` binds it as the `auto-data` workspace `model_hint`, the data-analysis lane that needs the larger context. The window is compiled into the tag with `portal models apply-params` because request-time context options are discarded by the API.

## Why

The `reasoning` group registration in `config/backends.yaml` and the `auto-data` `model_hint` in `config/portal.yaml` are the two config facts that give this 64K variant its identity. The unit cites both files because the long window exists specifically for that workspace, and the absence from `general` is itself a registry fact worth recording.
