---
id: unit-model-catalog-gemma4-e4b-it-qat-ctx8k
kind: what
title: "MODEL_CATALOG \u2014 `gemma4:e4b-it-qat-ctx8k`"
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
created_at: 1784946220.645856
updated_at: 1784946220.645856
---

`gemma4:e4b-it-qat-ctx8k` extends `gemma4:e4b-it-qat` with an 8192-token context bound. `config/backends.yaml` registers the derived id under the `vision` group with `supports_tools: true`, matching the parent's placement. The bound is materialized via `portal models apply-params` because per-request `options.num_ctx` is ignored by the completion API, forcing the cap into the tag itself. The parent model, not this id, is what the `bench-gemma4-e4b-qat` workspace selects as its `model_hint` in `config/portal.yaml`.

## Why

The derived tag's `vision` group entry in `config/backends.yaml` is the only registration that names it; the portal file binds the bench workspace to the parent instead. The unit therefore leans on the backend registry for its claims while noting the parent relationship, so the scope of every assertion stays within what the cited file actually records.
