---
id: unit-model-catalog-hf-co-unsloth-qwen-agentworld-35b-a3b-gguf-ud-q4-k-xl
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF:UD-Q4_K_XL`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: fb9979b75eb4d70f331e849b80fc7326e8e61847
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6119812
updated_at: 1784946220.6119812
---

`hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF:UD-Q4_K_XL` is a ~21GB Qwen3 MoE with 3B active parameters, a language world model trained on MCP, Terminal, SWE, Web, Android, OS, and Search environment simulation. `config/backends.yaml` registers it under both the `general` and `coding` groups, each with `supports_tools: true`. `config/portal.yaml` binds it as the `bench-agentworld` `model_hint` and records its 2026-06-25 promotion to the `auto-agentic` secondary slot at 45 TPS with an audit-tools pass; the heavy `auto-agentic` variant description also names it as fallback one. The `-ctx64k` derived tag is what the `auto-agentic` lite variant actually routes to.

## Why

The dual `general`/`coding` registration with `supports_tools: true` in both groups is asserted directly by `config/backends.yaml`, and `config/portal.yaml` supplies the promotion record and the bench binding. The institutional knowledge that this is an env-simulation world model complementing the heavier 80B coder is preserved because the workspace descriptions are precisely where that design role is documented.
