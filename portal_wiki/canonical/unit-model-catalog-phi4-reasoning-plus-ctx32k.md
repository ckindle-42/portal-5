---
id: unit-model-catalog-phi4-reasoning-plus-ctx32k
kind: what
title: "MODEL_CATALOG \u2014 `phi4-reasoning:plus-ctx32k`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: 64c5f5f41652bf67e97863ee1a6285289eaeea00
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.656215
updated_at: 1784946220.656215
---

`phi4-reasoning:plus-ctx32k` is the derived tag of `phi4-reasoning:plus` with `PARAMETER num_ctx 32768` baked in via the `apply-params` command. `config/backends.yaml` registers it in `group: coding` with `supports_tools: true`, but a comment there states it is intentionally NOT added to `group: reasoning` — confirmed to crash Ollama's llama-server on load, so it must stay unreachable from any production workspace until the crash resolves upstream. Its registration exists for catalog parity only. No `config/portal.yaml` workspace references the tag.

## Why

This derived tag is the exception case: registered in the coding backend for completeness while barred from the reasoning group where the base model's tooling would otherwise place it. Grounding to the backends.yaml registration and its crash comment makes the do-not-use status a config fact rather than prose. The parity-only nature is why no portal.yaml wiring exists for it.
