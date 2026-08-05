---
id: unit-model-catalog-huihui-ai-qwen3-5-abliterated-9b
kind: what
title: "MODEL_CATALOG \u2014 `huihui_ai/qwen3.5-abliterated:9b`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: db75e444cdca521f9be63059be9180bb380a4a64
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.61712
updated_at: 1784946220.61712
---

`huihui_ai/qwen3.5-abliterated:9b` is a ~5.8GB fast abliterated model optimized for TTP generation, registered in `config/backends.yaml` under both the `general` and `security` groups with `supports_tools: true` in each — a duplicate entry required so security-group routing resolves the correct model. `config/portal.yaml` binds the base id as the `bench-qwen35-abliterated` `model_hint` (the uncensored tool-capable AUTO baseline) while the red-team workspaces route the derived tags: the `auto-security` `redteam` and `purpleteam` variants use `:9b-ctx8k` and the `purpleteam-deep` variant uses `:9b-ctx64k`. It is the hop-0 red-team primary for the purple chains.

## Why

The duplicate `general`/`security` registration with `supports_tools: true` is asserted directly by `config/backends.yaml`, and `config/portal.yaml` shows exactly which workspace uses the base id versus which routes the derived tags. The institutional knowledge about the security-group routing requirement is preserved because the duplicate entry is itself the design mechanism that makes streaming hint resolution correct.
