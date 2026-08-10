---
id: unit-model-catalog-gpt-oss-20b
kind: what
title: "MODEL_CATALOG \u2014 `gpt-oss:20b`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 9c0a4efa9fea8836ee3466b206c01b042c59455f
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.631478
updated_at: 1784946220.631478
---

`gpt-oss:20b` is registered in `config/backends.yaml` under the `coding` group with `supports_tools: true`, the `reasoning` group with `supports_tools: true`, and the `general` group with `supports_tools: false`. `config/portal.yaml` binds it as the `bench-gptoss` workspace `model_hint` and the `auto-agentic` description lists it as fallback 2, describing an OpenAI open-weight MoE (~12GB, o3-mini level) purpose-built for agent/tool use with configurable thinking depth. The catalog records an audit-tools confirmation on 2026-06-18 after an earlier text-only mislabel, and the model was promoted to the auto-agentic fallback and coding pool.

## Why

The `coding` and `reasoning` group registrations in `config/backends.yaml` assert `supports_tools: true` while the `general` group keeps it false, which is the mechanical basis for its tool-capable status, and `config/portal.yaml` supplies the `bench-gptoss` binding and the auto-agentic fallback reference. The audit-tools confirmation and promotion note are institutional knowledge explaining why the flag is true.
