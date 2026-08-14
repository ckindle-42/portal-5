---
id: unit-general-tools-vendored-fleet
kind: mixed
title: "General tools \u2014 IDE-only vendored MCP fleet"
sources:
- type: code
  path: portal/modules/general/tools/__init__.py
  commit: 1a0e2df4
claims: []
confidence: high
tags:
- authored-v1
- module
- general
- tools
created_at: 1785794897.3152971
updated_at: 1785794897.3152971
---

The general module's base tool fleet is four externally vendored MCP
servers — filesystem, fetch, git, docker — declared in `config/portal.yaml`'s
`mcp_fleet` and rendered to `.mcp.json` by `sync-config`. `BASE_TOOL_FLEET_IDS`
names that roster as a constant.

## Why

All four are `expose_to_pipeline: false`, which is the whole point of the
arrangement: they are available to Claude Code and opencode for repository
work but are not callable by workspace personas through the pipeline. Keeping
them out of the pipeline is a security boundary as much as a scoping one —
a persona-triggerable filesystem or docker tool would be a much larger attack
surface than an IDE tool a human operator invokes. The module intentionally
has no Python wrapper code; the real implementation is the third-party package
each server runs.

## Interfaces

`BASE_TOOL_FLEET_IDS` is the only symbol, used as the module's roster
declaration. The operational surface is the fleet table in `portal.yaml` and
the rendered `.mcp.json`, both generated from that single source.
