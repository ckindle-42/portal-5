---
id: unit-module-coding
kind: mixed
title: "Coding Module \u2014 agentic coding + sandbox execution"
sources:
- type: code
  path: portal/modules/coding/tools/code_sandbox_mcp.py
- type: code
  path: portal/platform/inference/router/preinject.py
- type: code
  path: portal/platform/wiki/adapters/modules.py
- type: code
  path: config/portal.yaml
last_generated_commit: f5987f1ea6b0cdb25b66e33a02b95183205d0605
claims: []
confidence: high
tags:
- coding
- module
- verified-v1
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
    `_resolve_workspace_variant()` in `portal/platform/inference/router/preinject.py`):
  - `laguna` (was auto-coding-agentic) — Laguna-XS.2, agentic
  - `northmini` (was auto-coding-northmini) — North-Mini-Code, single-shot
  - `uncensored` (was auto-coding-uncensored) — OmniCoder-2, single-shot
  - `uncensored-agentic` (was auto-coding-uncensored-agentic) — Qwen3-Coder-Next abliterated, agentic
  - `heavy` (was auto-agentic) — Qwen3-Coder-Next, agentic
  - `lite` (was auto-agentic-lite) — Qwen-AgentWorld-35B-A3B, agentic
  - `ornith` (was auto-agentic-ornith) — Ornith-1.0-35B, agentic

(auto-devstral, auto-glm, auto-glm-thinking, auto-mistral deleted outright
in Phase 7 — model-tied workspaces, no distinguishing behavior beyond
model_hint; their personas moved to `workspace_model: auto-coding`.)

Also uses the general module's filesystem/git base tools for repo work.

## Module State

```yaml
enabled: true
```

## Why

The coding module is the largest always-on discipline after security, and
its unit is live config the same way every `unit-module-*` is: the
`enabled:` field is read by `portal/platform/wiki/adapters/modules.py`
(`_unit_enabled_state`) to gate `auto-coding` routing and the `execution`
sandbox fleet id, with a confirm-gated CLI write-back
(`writeback_module.py`) as the only allowed way to flip it. The variant
list above is grounded to the `variants:` block of the `auto-coding`
entry in `config/portal.yaml`, and variant selection itself is enforced
by `_resolve_workspace_variant()` in `preinject.py` — so this unit's prose
tracks both the config that declares the variants and the code that
applies them.
