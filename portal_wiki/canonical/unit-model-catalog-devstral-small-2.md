---
id: unit-model-catalog-devstral-small-2
kind: what
title: "MODEL_CATALOG \u2014 `devstral-small-2`"
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
created_at: 1784946220.607528
updated_at: 1784946220.607528
---

`devstral-small-2` is registered in `config/backends.yaml` under the `coding` backend group with `supports_tools: true`. `config/portal.yaml` references it in the `bench-devstral-small-2` workspace description as Devstral V2 (Dec 2025, Apache 2.0, 24B, ~14GB Q4) with 256K ctx, vision added, and improved SWE-bench over `devstral:24b`; that workspace's `model_hint` is the `devstral-small-2:latest` tag. Tool support is asserted per Mistral's function-calling format, with `--audit-tools` verification recommended before promotion.

## Why

The bare `devstral-small-2` id and the `devstral-small-2:latest` tag are distinct registry strings: only the bare id sits in the `coding` group with `supports_tools: true`, while `config/portal.yaml`'s bench workspace points its `model_hint` at the tagged form. Grounding the unit to both files records the V2 facts and the coding-group registration without conflating the two id spellings.
