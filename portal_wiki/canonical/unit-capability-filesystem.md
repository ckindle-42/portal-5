---
id: unit-capability-filesystem
kind: mixed
title: "Filesystem MCP \u2014 vendored IDE file access"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/general/tools/__init__.py
claims: []
confidence: high
tags:
- capability
- mcp
- general
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# Filesystem MCP — vendored IDE file access

## What

The Filesystem MCP is the externally vendored `@modelcontextprotocol/
server-filesystem` package, declared in `config/portal.yaml`'s `mcp_fleet`
under the `general` module and rendered to `.mcp.json` by `sync-config`. It is
IDE-only (`expose_to_pipeline: false`, `expose_to_ide: true`) and serves the
home projects directory and `/tmp`.

## How it's used

The server exposes the standard file-tool family — read, write, list, search,
and move operations — scoped to the roots it is launched with. An IDE agent
uses it for repository work that a pipeline workspace must not do: editing a
file on disk is an operator action, not a persona capability.

## Why it exists

The general module's whole design is that these base tools are vendored
third-party servers with no Portal wrapper code, and that they are deliberately
kept out of the pipeline. The rationale is a security boundary as much as a
scoping one: a persona-triggerable filesystem tool would be a much larger
attack surface than an IDE tool a human invokes.

## Value

An editing session gets full, correct file access without Portal maintaining a
filesystem implementation, and the boundary it enforces — read/write lives in
the IDE, never in a routed workspace — is exactly the containment the security
posture relies on.
