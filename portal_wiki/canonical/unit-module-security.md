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

- auto-security
- auto-security-uncensored
- auto-pentest
- auto-blueteam
- auto-redteam
- auto-redteam-deep
- auto-purpleteam
- auto-purpleteam-deep
- auto-purpleteam-exec

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
