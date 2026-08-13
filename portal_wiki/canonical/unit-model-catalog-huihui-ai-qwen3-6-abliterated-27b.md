---
id: unit-model-catalog-huihui-ai-qwen3-6-abliterated-27b
kind: what
title: "MODEL_CATALOG \u2014 `huihui_ai/Qwen3.6-abliterated:27b`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 75c5054f791636f367b62a1776bcc9f631794766
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6427011
updated_at: 1784946220.6427011
---

`huihui_ai/Qwen3.6-abliterated:27b` is a dense 27B Q4 abliterated model (~16-17GB), registered in `config/backends.yaml` under both the `general` and `creative` groups with `supports_tools: true` in each. `config/portal.yaml` binds it as the `bench-huihui-qwen36-27b` `model_hint`, benched head-to-head against the stock `qwen3.6:27b-q4_K_M` with PROMOTE_POLICY=confirm, and the `auto-general-uncensored` workspace routes the `:27b-ctx8k` variant. The general-group entry gives it AUTO routing; the creative-group entry gives the bench workspace creative routing. No standalone creative/music production workspace is currently wired to the base id.

## Why

The dual `general`/`creative` registration with `supports_tools: true` is asserted directly by `config/backends.yaml`, and `config/portal.yaml` shows the `bench-huihui-qwen36-27b` binding plus the `auto-general-uncensored` use of the derived tag. The older reference to a creative/music bench target was corrected to the actual `bench-huihui-qwen36-27b` id the config carries, keeping the body aligned with the registry.
