---
id: unit-module-security
kind: mixed
title: "Security Module \u2014 RBP (Red/Blue/Purple) bench engine"
sources:
- type: code
  path: portal/modules/security/tools/security_mcp.py
- type: code
  path: portal/modules/security/tools/proxmox_mcp.py
- type: code
  path: portal/platform/inference/router/preinject.py
- type: code
  path: portal/platform/wiki/adapters/modules.py
- type: code
  path: config/portal.yaml
last_generated_commit: aae69a16de501e8524f279c9bff13f3fdc241f32
claims: []
confidence: high
tags:
- module
- security
- verified-v1
created_at: 1783886831.981568
updated_at: 1783886831.981568
---

# Security Module — RBP (Red/Blue/Purple) bench engine

## Tools

portal.modules.security.tools.security_mcp — RBP capability index, goal-driven
decide, drift gate, capability graph (:8919); portal.modules.security.tools.proxmox_mcp
— lab lifecycle (Proxmox snapshot/restore, container exec)

## Workspaces

- auto-security (BUILD_PROGRAM_COLLAPSE_V1.md Phase 6 folded the 8 sibling
  security workspaces into this one, selected via a `variant:` query param
  or a persona's own `variant:` field — resolved by
  `_resolve_workspace_variant()` in `portal/platform/inference/router/preinject.py`):
  - `uncensored` (was auto-security-uncensored) — role=purple, guardrail=uncensored
  - `pentest` (was auto-pentest) — role=pentest
  - `blueteam` (was auto-blueteam) — role=blue
  - `redteam` (was auto-redteam) — role=red, depth=default
  - `redteam-deep` (was auto-redteam-deep) — role=red, depth=deep
  - `purpleteam` (was auto-purpleteam) — role=purple, depth=default
  - `purpleteam-deep` (was auto-purpleteam-deep) — role=purple, depth=deep
  - `purpleteam-exec` (was auto-purpleteam-exec) — role=purple, depth=exec

Two orchestration variants extend the fold and live in the same
`variants:` block of `config/portal.yaml`: `blueteam-orchestrated`
(blue-orchestration discovery pipeline) and `blueteam-council`
(multi-model council-of-agreement loop).

This is the largest structural module — the only one with core/, adapters/,
cli/, config/, eval/, knowledge/, tests/, tools/ all populated (see
CLAUDE.md Project Layout). Its workspace set is RBP-internal
(auto-*sec*/pentest/redteam/blueteam/purpleteam naming); tagging its
`module:` field on each workspace happens in
BUILD_PROGRAM_COLLAPSE_V1.md Phase 2.

## Module State

```yaml
enabled: true
```

## Why

The security module is the only RBP bench engine and the largest
structural surface in the tree, and its toggle carries the most routing
weight of any module: disabling it hides every `auto-security` variant
and both `security` and `proxmox` fleet ids at once. The `enabled:` field
is live config read by `portal/platform/wiki/adapters/modules.py`
(`_unit_enabled_state`), and the variant list is grounded to the
`variants:` block of the `auto-security` entry in `config/portal.yaml`.
This unit is sourced to the module adapter, the security tool servers it
gates, the preinject variant resolver, and `config/portal.yaml` so the
toggle and the workspace surface it controls stay verifiable together.
