---
id: unit-model-catalog-gemma4-e2b-it-qat-ctx8k
kind: what
title: "MODEL_CATALOG \u2014 `gemma4:e2b-it-qat-ctx8k`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: 64c5f5f41652bf67e97863ee1a6285289eaeea00
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.645519
updated_at: 1784946220.645519
---

`gemma4:e2b-it-qat-ctx8k` is the bounded-context sibling of `gemma4:e2b-it-qat`, carrying an 8192-token ceiling baked through `portal models apply-params`. `config/backends.yaml` places it in the `vision` group with `supports_tools: true`. The reason for a distinct tag is that the `/v1/chat/completions` API discards request-time context limits, so per-workspace bounds must be compiled into the model name itself. `config/portal.yaml` does not reference this id; only the backend registry holds it.

## Why

Grounding comes from the `vision` group registration in `config/backends.yaml` alone, because no workspace in `config/portal.yaml` lists this tag. The unit documents the parent's full profile elsewhere and restricts its own scope to the derived-id registration and the context-cap mechanism, which keeps every claim checkable against the cited file.
