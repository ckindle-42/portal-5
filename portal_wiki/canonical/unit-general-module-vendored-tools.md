---
id: unit-general-module-vendored-tools
kind: mixed
title: "General module \u2014 config-only, vendored base tools"
sources:
- type: code
  path: portal/modules/general/__init__.py
  commit: 1a0e2df4
claims: []
confidence: high
tags:
- authored-v1
- module
- general
created_at: 1785794886.0219789
updated_at: 1785794886.0219789
---

The general module is the always-on base discipline and the template proof
that a non-security module can be relocated cleanly. Unlike security, which
moved a large Portal-owned codebase intact, general has no Portal-authored
source to relocate: its four tools are externally vendored MCP servers
(filesystem, fetch, git, docker) declared in `config/portal.yaml`'s `mcp_fleet`
and consumed IDE-side by Claude Code and opencode, not through the pipeline.

## Why

The module records the real, existing surface rather than fabricating wrapper
code for tools Portal does not own. The distinction matters to the module
toggling discipline: a module whose tools are all `expose_to_pipeline: false`
still owns its workspaces and their routing, and the module tag is what
`sync-config` uses to hide or show those workspaces. Documenting this shape in
the namespace marker stops a future task from inventing a redundant wrapper
layer around third-party servers that already speak MCP.

## Interfaces

The `__init__.py` declares no callable surface — the package is the namespace
for the module and the place its docstring records the vendored-tool
arrangement. The actual fleet declaration lives in `portal.yaml`'s `mcp_fleet`
and the workspace roster in the same file's `workspaces` mapping.
