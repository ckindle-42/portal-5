---
id: unit-model-catalog-granite4-1-30b
kind: what
title: "MODEL_CATALOG \u2014 `granite4.1:30b`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 41df61e0a6102275a700700e9765972f1508c4c5
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6331468
updated_at: 1784946220.6331468
---

`granite4.1:30b` is registered in `config/backends.yaml` under the `reasoning` group with `supports_tools: true` and under the `general` group with `supports_tools: false` (bench-only intake). `config/portal.yaml` describes it in the `bench-granite41-30b` workspace entry as a dense 30B no-think model (~17GB Q4_K_M, Apache 2.0, ISO-certified, cryptographic signatures) with BFCL V3 73.7 (#1 on the IBM chart), IFEval 89.7, GSM8K 94.2, and EvalPlus 82.7, trained with GRC data curation for compliance and audit workflows; that workspace's `model_hint` is the derived `granite4.1:30b-ctx16k` tag.

## Why

The `reasoning` group registration in `config/backends.yaml` asserts `supports_tools: true` while the general group keeps it false, and `config/portal.yaml` supplies the benchmark scores and the GRC compliance framing. The unit is grounded to both files because the model's reasoning-pool placement and its workspace description come from different config sources.
