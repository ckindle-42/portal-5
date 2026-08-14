---
id: unit-module-cad
kind: mixed
title: "CAD Module \u2014 OpenSCAD/CadQuery 3D model generation"
sources:
- type: code
  path: portal/modules/cad/tools/cad_render_mcp.py
- type: code
  path: portal/platform/wiki/adapters/modules.py
- type: code
  path: config/portal.yaml
last_generated_commit: 41df61e0a6102275a700700e9765972f1508c4c5
claims: []
confidence: high
tags:
- cad
- module
- verified-v1
created_at: 1783821386.7899158
updated_at: 1783821386.7899158
---

# CAD Module — OpenSCAD/CadQuery 3D model generation

## Tools

`portal.modules.cad.tools.cad_render_mcp` — the CAD render MCP server,
registered as `cad_render` in `config/portal.yaml` `mcp_fleet:` on port
8926. It is pipeline-exposed only (`expose_to_pipeline: true`,
`expose_to_ide: false`), so its tools reach workspace personas but not the
IDE.

## Workspaces

- `auto-cad` — 3D model generation for CAD / 3D-printing design, routed to
  the module's workspaces by the `module:` tag on the portal.yaml entry.

## Module State

```yaml
enabled: true
```

## Why

This is a live-config module unit, not a description: the fenced
`enabled:` value is read by `portal/platform/wiki/adapters/modules.py`
(`_unit_enabled_state`) to decide whether `auto-cad` routes and whether
`cad_render` launches in the MCP fleet, so flipping it is a real state
change gated by the CLI write-back (`writeback_module.py`). The unit is
the toggle's single source of truth, and re-grounding it to the adapter
plus the module's own tool code keeps the toggle honest against the code
it actually controls.
