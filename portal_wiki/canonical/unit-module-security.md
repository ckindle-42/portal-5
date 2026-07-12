---
id: unit-module-security
kind: mixed
title: "Security Module — RBP (Red/Blue/Purple) bench engine"
sources:
- type: code
  path: portal/modules/security/
- type: design
  path: coding_task/BUILD_PROGRAM_MODULARIZATION_ALL_V1.md
last_generated_commit: ''
confidence: high
tags:
- module
- security
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
  `resolve_workspace_variant()` in `portal/platform/inference/router/preinject.py`):
  - `uncensored` (was auto-security-uncensored) — role=purple, guardrail=uncensored
  - `pentest` (was auto-pentest) — role=pentest
  - `blueteam` (was auto-blueteam) — role=blue
  - `redteam` (was auto-redteam) — role=red, depth=default
  - `redteam-deep` (was auto-redteam-deep) — role=red, depth=deep
  - `purpleteam` (was auto-purpleteam) — role=purple, depth=default
  - `purpleteam-deep` (was auto-purpleteam-deep) — role=purple, depth=deep
  - `purpleteam-exec` (was auto-purpleteam-exec) — role=purple, depth=exec

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
