---
id: unit-capability-binresearch
kind: mixed
title: "BinResearch MCP \u2014 static binary reverse-engineering arsenal"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/binary_research/tools/binresearch_mcp.py
- type: code
  path: deploy/portal-5/docker-compose.yml
claims: []
confidence: high
tags:
- capability
- mcp
- platform
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# BinResearch MCP — static binary reverse-engineering arsenal

## What

The BinResearch MCP (`portal/modules/binary_research/tools/binresearch_mcp.py`,
port 8930) exposes a static reverse-engineering toolchain against a DinD
container built from `Dockerfile.binresearch`. It is IDE-exposed
(`expose_to_pipeline: false`, `expose_to_ide: true`): an operator agent invokes
it from the IDE, not from a pipeline workspace.

## How it's used

Three tools form the surface: `re_tools` (what RE tooling exists in the arsenal
image), `re_exec` (run a shell command against a project inside the DinD
container), and `re_python` (run a Python snippet with the RE libraries
available). Each project lives under the bind-mounted
`${BINRESEARCH_PROJECTS_ROOT}` tree, so a `docker run -v` issued by `re_exec`
resolves on the daemon filesystem exactly like the compose mount that provisions
it.

## Why it exists

Binary analysis needs a hermetic toolchain — radare2, capstone, and friends —
that should never pollute the host or a general sandbox. Wrapping it in a
purpose-built image keeps the tooling versioned and reproducible while the MCP
layer gives an agent a small, typed surface instead of raw container shell
access. The `-exec`-style trust boundary is why it stays out of the pipeline.

## Value

An operator can reverse a binary end to end from the IDE — inspect, disassemble,
script — without Dockerfile surgery or host installs. The evidence trail stays
in the project tree, and the arsenal image can be rebuilt (`./launch.sh
build-binresearch`) without disturbing any other surface.
