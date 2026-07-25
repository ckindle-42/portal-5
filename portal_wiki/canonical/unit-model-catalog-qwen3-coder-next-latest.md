---
id: unit-model-catalog-qwen3-coder-next-latest
kind: what
title: "MODEL_CATALOG \u2014 `qwen3-coder-next:latest`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: '`qwen3-coder-next:latest`'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.612763
updated_at: 1784946220.612763
---

Qwen3-Coder-Next (Alibaba, Feb 2026, Apache 2.0, 80B total / 3B active MoE, ~46GB Q4, 256K ctx). Novel hybrid architecture: Gated DeltaNet + Gated Attention + MoE. Non-reasoning for ultra-fast code responses. Agentic training on 800K executable tasks with RL. Fits 64GB unified memory (~18GB headroom). Fast TPS due to 3B active. Wires pre-existing bench-qwen3-coder-next workspace (TASK_MODEL_REFRESH_V8 A17). supports_tools=true: audit-tools 2026-06-21 confirmed tool_call (6.8s) — retest resolved prior 2026-06-18 ERROR (model had been evicted during that probe).
