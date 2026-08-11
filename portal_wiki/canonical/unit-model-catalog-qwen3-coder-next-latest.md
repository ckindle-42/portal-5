---
id: unit-model-catalog-qwen3-coder-next-latest
kind: what
title: "MODEL_CATALOG \u2014 `qwen3-coder-next:latest`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 1896bb7da29dd96ff280b8ffb495519d507070ee
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.612763
updated_at: 1784946220.612763
---

`qwen3-coder-next:latest` is an 80B-total / 3B-active MoE agentic coder (Alibaba, Apache 2.0, non-reasoning for fast code responses, ~46GB Q4, 256K context) that fits 64GB unified memory with roughly 18GB headroom, and its small active size is why throughput stays fast. `config/backends.yaml` registers it twice: `group: general` (`ollama-general`) lists it with `supports_tools: false` as a conservative unprobed default, while `group: coding` (`ollama-coding`) lists it with `supports_tools: true` — the value the audit-tools 2026-06-21 probe confirmed with a tool_call after a prior probe errored on an evicted model. `config/portal.yaml` uses the base tag as the `model_hint` of the `bench-qwen3-coder-next` eval workspace, whose description documents the hybrid Gated DeltaNet + MoE architecture and 800K-task agentic RL training. The derived `qwen3-coder-next:latest-ctx64k` tag wires the heavy auto-coding variant.

## Why

The base tag's `supports_tools` value cannot be stated as a single fact: backends.yaml disagrees between groups, and the coding-group `true` is the live-probed answer while the general-group `false` is the unprobed conservative default. Naming both groups and both flags is the only accurate grounding, and it explains why the coding lane trusts this model for tool dispatch while the general pool does not.
