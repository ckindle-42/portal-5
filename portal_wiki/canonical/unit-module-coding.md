---
id: unit-module-coding
kind: mixed
title: "Coding Module \u2014 agentic coding + sandbox execution"
sources:
- type: code
  path: portal/modules/coding/
- type: design
  path: coding_task/BUILD_PROGRAM_MODULARIZATION_ALL_V1.md
last_generated_commit: ''
confidence: high
tags:
- module
- coding
created_at: 1783821386.783052
updated_at: 1783821386.783052
---

# Coding Module — agentic coding + sandbox execution

## Tools

portal.modules.coding.tools.code_sandbox_mcp — isolated code execution (:8914)

## Workspaces

- auto-coding (BUILD_PROGRAM_COLLAPSE_V1.md Phase 5 folded the 8 sibling
  coding/agentic workspaces into this one, selected via a `variant:` query
  param or a persona's own `variant:` field — resolved by
  `resolve_workspace_variant()` in `portal/platform/inference/router/preinject.py`):
  - `laguna` (was auto-coding-agentic) — Laguna-XS.2, agentic
  - `northmini` (was auto-coding-northmini) — North-Mini-Code, single-shot
  - `uncensored` (was auto-coding-uncensored) — OmniCoder-2, single-shot
  - `uncensored-agentic` (was auto-coding-uncensored-agentic) — Qwen3-Coder-Next abliterated, agentic
  - `heavy` (was auto-agentic) — Qwen3-Coder-Next, agentic
  - `lite` (was auto-agentic-lite) — Qwen-AgentWorld-35B-A3B, agentic
  - `ornith` (was auto-agentic-ornith) — Ornith-1.0-35B, agentic
- auto-devstral (still separate — model-tied workspace deletion is Phase 7)

Also uses the general module's filesystem/git base tools for repo work.

## Module State

```yaml
enabled: true
```
