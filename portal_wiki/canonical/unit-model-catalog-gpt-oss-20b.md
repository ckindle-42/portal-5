---
id: unit-model-catalog-gpt-oss-20b
kind: what
title: "MODEL_CATALOG \u2014 `gpt-oss:20b`"
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
created_at: 1784946220.631478
updated_at: 1784946220.631478
---
`config/backends.yaml` lists it with `supports_tools: true` in every group (verified 2026-09-25 by a neutral native tool-call probe — 3/3 single-call plus a clean tool-result turn); the router reads one flag per model id, last entry wins, so a per-group split never took effect. `config/portal.yaml` binds it as the `bench-gptoss` workspace `model_hint` and the `auto-agentic` description lists it as fallback 2, describing an OpenAI open-weight MoE (~12GB, o3-mini level) purpose-built for agent/tool use with configurable thinking depth. The catalog records an audit-tools confirmation on 2026-06-18 after an earlier text-only mislabel, and the model was promoted to the auto-agentic fallback and coding pool.

## Why

The `coding` and `reasoning` group registrations in `config/backends.yaml` assert `supports_tools: true` while the `general` group keeps it false, which is the mechanical basis for its tool-capable status, and `config/portal.yaml` supplies the `bench-gptoss` binding and the auto-agentic fallback reference. The audit-tools confirmation and promotion note are institutional knowledge explaining why the flag is true.
