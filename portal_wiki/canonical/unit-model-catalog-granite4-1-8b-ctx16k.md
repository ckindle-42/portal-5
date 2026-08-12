---
id: unit-model-catalog-granite4-1-8b-ctx16k
kind: what
title: "MODEL_CATALOG \u2014 `granite4.1:8b-ctx16k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: a23f47b3e687df1693600eeea5b4f3f381b9da20
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.646517
updated_at: 1784946220.646517
---

`granite4.1:8b-ctx16k` is a derived context-capped tag of `granite4.1:8b`. It appears in `config/backends.yaml` under the `general`, `security`, and `reasoning` groups, always with `supports_tools: true`. In `config/portal.yaml` it is the `model_hint` for `auto-documents`, `auto-image`, `auto-video`, and `auto-compliance` — the tool-calling MCP lanes for documents, image generation, video, and compliance analysis all route on this 16K-context variant. The cap is baked in via `portal models apply-params` because Ollama's `/v1/chat/completions` ignores request-time `options.num_ctx`; a derived tag is the only way to bound context per workspace. See the base `granite4.1:8b` entry for full model detail; this unit exists to satisfy backends.yaml/MODEL_CATALOG parity.

## Why

The previous body cited only `config/MODEL_CATALOG.md` and asserted the context-cap mechanism from doc prose. Re-grounding pins the tag to `config/backends.yaml`, which declares `granite4.1:8b-ctx16k` in three groups with `supports_tools: true` in each, and to `config/portal.yaml`, which selects it as the `model_hint` for four workspaces. Every claim now traces to a machine-read config file rather than a doc string.
