---
id: unit-known-limitations-auto-math-workspace-reasoning-block-support
kind: what
title: "KNOWN_LIMITATIONS \u2014 auto-math Workspace \u2014 Reasoning Block Support"
sources:
- type: code
  path: config/portal.yaml
last_generated_commit: 0fec84d46a8898b1b5baf0508af1e25634b099af
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.665893
updated_at: 1784946220.665893
---

- **ID**: P5-MATH-001
- **Status**: RESOLVED (V8 model refresh — 2026-06-10)
- **History**: The `auto-math` workspace once ran a math-tuned model whose responses carried no separate reasoning channel, so step-by-step thought was not surfaced as a collapsible block. The V8 refresh replaced that primary with `phi4-mini-reasoning:latest-ctx24k`, and `config/portal.yaml` now records `emits_reasoning: true` for the workspace (`model_hint`, `context_limit: 24576`, `tools: []`).
- **Alternative**: For heavier reasoning, `auto-reasoning` (`DeepSeek-R1-0528-Qwen3-8B`, `emits_reasoning: true`) also separates reasoning content.

## Why

The workspace's `emits_reasoning` flag is the routing contract that tells the pipeline and Open WebUI how to render the model's thinking: when true, reasoning is delivered as a distinct block the chat UI can collapse. Recording it per-workspace in `config/portal.yaml` rather than inferring from the model name keeps the presentation contract explicit and auditable against the live config.
