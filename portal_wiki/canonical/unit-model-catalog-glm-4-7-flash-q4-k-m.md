---
id: unit-model-catalog-glm-4-7-flash-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `glm-4.7-flash:Q4_K_M`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 86e6f142c0069ca2d4824b4721a545e64bd585b3
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6146472
updated_at: 1784946220.6146472
---

`glm-4.7-flash:Q4_K_M` is registered in `config/backends.yaml` under the `coding` group with `supports_tools: true`, the `security` group with `supports_tools: true`, and the `general` group with `supports_tools: false`. `config/portal.yaml` binds it as the `bench-glm` workspace `model_hint` and the `auto-security` description names it the strongest candidate on generic tool reliability, describing a ZhipuAI / Z.AI MIT-licensed 31B MoE (4 experts/token, ~3B active, 128K context) of non-Meta/Qwen lineage. The catalog records the 2026-07-16 re-verification: direct probes and an audit-tools run confirmed clean tool calls, and the kerberoast chain scored valid_rate 1.00 with redundant_call_rate 0.00, which is why `supports_tools` was flipped to true in `config/backends.yaml`. The `:math` variant is not pulled.

## Why

The tool-capable status is asserted by the `coding` and `security` group registrations in `config/backends.yaml` (the general group keeps it false), and `config/portal.yaml` supplies the `bench-glm` binding plus the `auto-security` tool-reliability note. The re-verification history is institutional knowledge that explains why the flag was flipped; the config files are the source for the id, its groups, and the current flag values.
