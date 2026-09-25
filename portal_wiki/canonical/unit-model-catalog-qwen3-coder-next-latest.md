---
id: unit-model-catalog-qwen3-coder-next-latest
kind: what
title: "MODEL_CATALOG \u2014 `qwen3-coder-next:latest`"
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
created_at: 1784946220.612763
updated_at: 1784946220.612763
---
`qwen3-coder-next:latest` is an 80B-total / 3B-active MoE agentic coder (Alibaba, Apache 2.0, non-reasoning for fast code responses, ~46GB Q4, 256K context) that fits 64GB unified memory with roughly 18GB headroom, and its small active size is why throughput stays fast. `config/backends.yaml` lists it with `supports_tools: true` in every group (verified 2026-09-25 by a neutral native tool-call probe — its portal5/qwen3-coder-next:latest-ctx256k derivative: 3/3 single-call plus a clean tool-result turn); the router reads one flag per model id, last entry wins, so a per-group split never took effect. `config/portal.yaml` uses the base tag as the `model_hint` of the `bench-qwen3-coder-next` eval workspace, whose description documents the hybrid Gated DeltaNet + MoE architecture and 800K-task agentic RL training. The derived `qwen3-coder-next:latest-ctx64k` tag wires the heavy auto-coding variant.

## Why

The router keeps one tool flag per model id (last entry wins), so the old general-`false` / coding-`true` split never meant what it seemed to. The 2026-09-25 probe of its `portal5/qwen3-coder-next:latest-ctx256k` derivative (same weights, 3/3 plus a clean tool-result turn) settled it: every entry is now `true`.
