---
id: unit-module-compliance
kind: mixed
title: "Compliance Module \u2014 multi-framework compliance mapping (config-only)"
sources:
- type: code
  path: portal/modules/security/core/compliance_report.py
- type: code
  path: portal/platform/wiki/adapters/modules.py
- type: code
  path: config/portal.yaml
last_generated_commit: aae69a16de501e8524f279c9bff13f3fdc241f32
claims: []
confidence: high
tags:
- compliance
- module
- verified-v1
created_at: 1783821386.790902
updated_at: 1783821386.790902
---

# Compliance Module — multi-framework compliance mapping (config-only)

## Tools

No dedicated MCP server of its own; compliance analysis reuses the
security module's `compliance_report.py` (`portal/modules/security/core/`),
which the security workspace tool surface already exposes.

## Workspaces

- `auto-compliance` — compliance mapping workspace, routed by its
  `module: compliance` tag in `config/portal.yaml`.

Config-only module, same pattern as general — no Portal-owned tool code
to relocate.

## Module State

```yaml
enabled: true
```

## Why

The compliance module is config-only: it owns a workspace but no MCP
server, so toggling it affects routing (`auto-compliance`) and nothing in
the fleet. That is exactly why this unit is live config rather than a
description — `portal/platform/wiki/adapters/modules.py` reads the fenced
`enabled:` field to gate the workspace, and the module's actual analysis
capability lives in the security module it depends on. Keeping the unit
sourced to the adapter plus `config/portal.yaml` makes the toggle's real
blast radius visible.
