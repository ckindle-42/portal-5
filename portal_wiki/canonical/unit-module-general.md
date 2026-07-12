---
id: unit-module-general
kind: mixed
title: "General Module \u2014 the always-on base (filesystem/fetch/git/docker)"
sources:
- type: code
  path: portal/modules/general/
- type: code
  path: config/portal.yaml#mcp_fleet
last_generated_commit: ''
confidence: high
tags:
- module
- general
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

```yaml
module: general
enabled: true
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
