---
id: unit-model-catalog-huihui-ai-qwen3-abliterated-14b-v2
kind: what
title: "MODEL_CATALOG \u2014 `huihui_ai/qwen3-abliterated:14b-v2`"
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
created_at: 1784946220.5983932
updated_at: 1784946220.5983932
---

`huihui_ai/qwen3-abliterated:14b-v2` is the huihui-ai Qwen3-14B abliteration v2, a V13 tier-gap fill between the 9B and 27B/35B classes, pulled as v2 only because v1 was explicitly retired by the author for garbled-output bugs. `config/backends.yaml` registers it under the `coding` group with `supports_tools: true` (a clean tool_calls probe confirmed this) and under the `general` group with `supports_tools: false`. `config/portal.yaml` binds it as the `bench-qwen3-14b-abliterated` `model_hint`, noting the native `<think>` opening tag was missing from the probe — a soft warning that does not block intake. It shares the same trusted huihui_ai native-tag lineage as `E2b-qat`.

## Why

The `coding`-group `supports_tools: true` versus `general`-group `false` split is asserted directly by `config/backends.yaml`, and `config/portal.yaml` supplies the `bench-qwen3-14b-abliterated` binding plus the probe caveat. The institutional knowledge about the v1 retirement and the missing-think-tag soft warning is preserved because both are recorded in the config comment and bench description, which are now the cited sources.
