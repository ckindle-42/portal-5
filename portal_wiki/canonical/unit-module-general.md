---
id: unit-module-general
kind: mixed
title: "General Module \u2014 the always-on base (filesystem/fetch/git/docker)"
sources:
- type: code
  path: portal/modules/general/tools/__init__.py
- type: code
  path: portal/modules/general/config/__init__.py
- type: code
  path: portal/platform/wiki/adapters/modules.py
- type: code
  path: config/portal.yaml#mcp_fleet
claims:
- probe: modules.enabled
  contains: general
confidence: high
tags:
- general
- module
- verified-v1
created_at: 1783815451.164374
updated_at: 1783815451.164374
---

# General Module — the always-on base

## What it is

The general module is the always-on base discipline: filesystem, fetch,
git, and docker access for IDE-side (Claude Code / opencode) repo work.
Unlike other modules, it wraps no Portal-authored source — its tools are
externally vendored MCP servers.

## Config (fenced yaml — DESIGN-MODULES-V1 module-definition convention)

The switch is `modules.general.enabled` in `config/portal.yaml` (`portal module enable|disable` writes it). This unit documents the switch; it does not hold it.

```yaml
module: general
tools:
  - filesystem
  - fetch
  - git
  - docker
workspaces:
  - auto-daily
  - auto-general-uncensored
expose_to_pipeline: false
expose_to_ide: true
```

## Structure

- portal/modules/general/tools/ — documents the 4 vendored MCP servers
  (BASE_TOOL_FLEET_IDS), no wrapper implementation (none needed/owned)
- portal/modules/general/config/ — general_workspaces(), a name-based
  pointer into config/portal.yaml (the single source of truth)

## Why

The general module is "always-on" in a way the other modules are not:
`modules.general.enabled` is true, and even if it were flipped the adapter
(`portal/platform/wiki/adapters/modules.py`) keeps the four base fleet ids
launched unconditionally because repo-facing tooling must never disappear
on a module toggle. The fenced block above is the DESIGN-MODULES-V1
module definition (tools and workspaces); it does not hold the switch.
The unit is sourced to the adapter, the two small files under
`portal/modules/general/` that document the fleet and the workspace
pointer, and the `mcp_fleet` section of `config/portal.yaml` that
declares the vendored servers.
