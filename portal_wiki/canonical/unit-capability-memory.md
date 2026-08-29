---
id: unit-capability-memory
kind: mixed
title: "Memory MCP \u2014 cross-conversation persistence"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/platform/memory/memory_mcp.py
- type: code
  path: config/inference/tools_manifest_memory_mcp.json
claims: []
confidence: high
tags:
- capability
- mcp
- platform
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# Memory MCP — cross-conversation persistence

## What

The Memory MCP (`portal/platform/memory/memory_mcp.py`, port 8920) stores and
recalls facts across conversations. It is pipeline- and IDE-exposed and is the
persistence layer several workspaces grant (`remember` / `recall` appear in
the `auto-coding` and tools-specialist tool lists).

## How it's used

`remember` writes a fact into persistent storage; `recall` retrieves what
matches a query; `forget` removes a specific memory; `list_memories` and
`clear_memories` enumerate and wipe the store. The unit behind the interface is
a structured memory store rather than free text, so recall returns candidate
memories an agent can verify against context.

## Why it exists

The pipeline is stateless by design — Open WebUI owns conversation state — but
an agent still needs a deliberately-opened channel to persist facts across
sessions. A dedicated memory MCP gives that channel an explicit write path, an
explicit query path, and an explicit deletion path, all governed by the
workspace tool grant rather than by ambient state an agent cannot audit.

## Value

Facts learned in one session — a user's preferences, a standing decision, an
environment detail — survive into the next without a human restating them, and
the explicit lifecycle tools mean the store stays auditable and cleanable
rather than an opaque accumulation.
