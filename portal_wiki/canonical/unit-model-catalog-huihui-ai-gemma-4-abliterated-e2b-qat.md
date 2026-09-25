---
id: unit-model-catalog-huihui-ai-gemma-4-abliterated-e2b-qat
kind: what
title: "MODEL_CATALOG \u2014 `huihui_ai/gemma-4-abliterated:E2b-qat`"
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
created_at: 1784946220.6199071
updated_at: 1784946220.6199071
---
`config/backends.yaml` lists it with `supports_tools: true` in every group (verified 2026-09-25 by a neutral native tool-call probe — 3/3 single-call plus a clean tool-result turn); the router reads one flag per model id, last entry wins, so a per-group split never took effect. `config/portal.yaml` binds it as the `bench-e2b-pentest` and `bench-exec-reasoning` `model_hint`s, where it was the 2026-06-24 exec-chain winner at 80% EXPLOIT-slot fill and 71.6 t/s, replacing Qwable-35B. The `auto-security` pentest variant description records that its earlier auto-pentest promotion was superseded on 2026-07-16: re-tested under the corrected reliability methodology it failed the gate at valid_rate 0.50-0.67, so the pentest lane now routes a different model. The head-to-head win and the memory savings remain historical context.

## Why

The `security`-group `supports_tools: true` versus `general`-group `false` split is asserted directly by `config/backends.yaml`, and `config/portal.yaml` supplies both the bench bindings and the supersession note in the pentest variant description. The promotion-and-reversal history is preserved because the portal description records exactly why the model was promoted and then demoted, which the registry flags alone would not convey.
