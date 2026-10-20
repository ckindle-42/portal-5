---
id: unit-wiki-adapter-modules
kind: mixed
title: "Wiki module adapter — toggle resolver (config holds the switch)"
sources:
- type: code
  path: portal/platform/wiki/adapters/modules.py
  commit: 94445e95
claims: []
confidence: high
tags:
- authored-v1
- wiki
- adapter
created_at: 1785797567.106965
updated_at: 1785797567.106965
---

The module toggle resolver answers the three resolver questions the module
gates need: which workspaces belong to a module, which MCP ids a module
launches, and which modules are enabled. It lives in the adapters layer
because `launched_mcp_ids` needs the live `mcp_fleet` id list from
`portal.platform.inference.config`, which the Portal-agnostic wiki core may
never import.

## Why

Enabled/disabled state lives in `config/portal.yaml` under
`modules.<name>.enabled`. `portal module enable|disable` writes that one
line. Each `unit-module-<name>` unit documents the switch; it does not hold
it. The resolver reads the config value and cross-references it against the
module-to-workspace and module-to-fleet maps (derived from each entry's
`module:` tag in `config/portal.yaml`, never hand-maintained). This is the
mechanical hook that makes the module toggle real: `enabled_modules()`
decides what the workspace dict and the MCP fleet actually contain, and the
eval module additionally honours `PORTAL_ENABLE_EVAL` as a bench-harness
opt-in.

## Interfaces

`module_workspace_ids()` and `module_mcp_ids()` return the derived maps;
`enabled_modules()` returns the enabled set (with the eval opt-in);
`launched_mcp_ids(mods)` returns the fleet ids a set of modules launches.

## Gotchas

A missing key falls back to the defaults: `eval`, `music`, and `video` off,
everything else on (including `image`). The shipped `modules:` block turns
image, music, and video off. Bench apparatus still opts in through that
block or `PORTAL_ENABLE_EVAL`.
