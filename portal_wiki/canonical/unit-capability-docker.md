---
id: unit-capability-docker
kind: mixed
title: "Docker MCP \u2014 vendored IDE container control"
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

# Docker MCP — vendored IDE container control

## What

The Docker MCP is the externally vendored `mcp-docker-server` package
(`npx -y mcp-docker-server`), declared in `config/portal.yaml`'s `mcp_fleet`
under the `general` module. It is IDE-only (`expose_to_pipeline: false`,
`expose_to_ide: true`), rendered to `.mcp.json` by `sync-config`.

## How it's used

The server exposes the docker surface — container and image list, inspect,
exec, and log operations — against the host daemon the IDE session runs on. An
operator agent uses it to inspect running services and container state while
debugging the stack.

## Why it exists

Docker is the fourth and heaviest of the general module's vendored base tools.
The rule is consistent across all four: they are external servers with no
Portal wrapper code, and none of them is persona-triggerable. A routed
workspace with a raw docker tool would be the largest attack surface in the
platform, so the capability is reserved for the human-invoked IDE lane.

## Value

Live container diagnostics stay inside the editing session — check a health
state, read a log, exec into a debug container — while the containment rule
holds everywhere else: pipeline personas can never create or mutate containers,
only the sandbox's purpose-built envelope can.
