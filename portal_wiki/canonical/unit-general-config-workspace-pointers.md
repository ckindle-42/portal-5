---
id: unit-general-config-workspace-pointers
kind: mixed
title: "General config \u2014 portal.yaml pointer surface"
sources:
- type: code
  path: portal/modules/general/config/__init__.py
  commit: 1a0e2df4
claims: []
confidence: high
tags:
- authored-v1
- module
- general
- config
created_at: 1785794891.7058592
updated_at: 1785794891.7058592
---

The general module's config surface is a name-based pointer into
`config/portal.yaml`, the single source of truth for workspaces.
`GENERAL_WORKSPACE_IDS` lists the two workspaces belonging to this discipline
(`auto-daily`, `auto-general-uncensored`) and `general_workspaces()` reads the
live portal config and returns their current entries.

## Why

`portal.yaml` has no per-workspace module tag stored inside the workspace spec
itself — the module association is by name convention, so this constant is the
roster that makes that convention explicit and machine-usable. Loading through
`load_portal_config()` at call time means the accessor always reflects the
config that actually routes these workspaces; a cached copy would drift the
moment the YAML changed, which is the exact staleness failure the drift-census
program exists to catch.

## Interfaces

`GENERAL_WORKSPACE_IDS` is the discipline roster and `general_workspaces()`
materialises the current entries from portal.yaml via
`cfg.workspaces[wid].model_dump()` — the returned shape follows the config
model rather than a hand-maintained projection.
