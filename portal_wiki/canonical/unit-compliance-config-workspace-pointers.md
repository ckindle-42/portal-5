---
id: unit-compliance-config-workspace-pointers
kind: mixed
title: "Compliance config \u2014 portal.yaml pointer surface"
sources:
- type: code
  path: portal/modules/compliance/config/__init__.py
  commit: 1a0e2df4
last_generated_commit: 1a0e2df4
claims: []
confidence: high
tags:
- authored-v1
- module
- compliance
- config
created_at: 1785794866.570522
updated_at: 1785794866.570522
---

The compliance module's config surface is a name-based pointer into
`config/portal.yaml` rather than a duplicate store. `COMPLIANCE_WORKSPACE_IDS`
lists the workspaces that belong to this discipline, and
`compliance_workspaces()` loads the live portal config and returns the matching
entries as dicts.

## Why

CLAUDE.md Rule 6 makes `config/portal.yaml` the single source of truth for
workspaces. A module that cached its own copy of `auto-compliance`'s spec
would drift from the real config the moment the YAML changed — the same
staleness failure the whole spine-drift program exists to catch. Reading
through `load_portal_config()` at call time means the module can never
disagree with the file that actually routes the workspace.

## Interfaces

`COMPLIANCE_WORKSPACE_IDS` is the module's roster constant and
`compliance_workspaces()` is the accessor that materialises the current
entries from portal.yaml — the shape returned mirrors the config model
(`cfg.workspaces[wid].model_dump()`), not a hand-maintained projection.
