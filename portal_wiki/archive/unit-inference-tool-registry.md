---
id: unit-inference-tool-registry
kind: mixed
title: "Inference tool registry \u2014 live MCP tool discovery"
sources:
- type: code
  path: portal/platform/inference/tool_registry.py
  commit: 5fbf51f8
last_generated_commit: 5fbf51f8
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
created_at: 1785797772.268832
updated_at: 1785797772.268832
---

`tool_registry.py` is the MCP tool registry: it discovers the pipeline's
tool servers, probes their manifests over HTTP, and builds the `ToolRegistry`
the router uses to dispatch tool calls. It holds the fleet table derived from
the portal config and refreshes the live tool definitions from the servers.

## Why

Tool dispatch needs a live, current map of tool names to their definitions
and their serving workspaces — a stale registry dispatches to a tool that
moved, or refuses a tool that exists. The registry owns that freshness: it
builds from the configured fleet (`get_pipeline_mcp_servers`), probes each
server's manifest, and caches the result with backoff on probe failures so a
down server does not block dispatch forever. The per-tool definition carries
the workspace authorisation, which is what lets the router decide whether a
persona may call a tool.

## Interfaces

`ToolDefinition` is the per-tool shape; `ToolRegistry` is the discovery +
cache + lookup surface with `get`, `refresh`, and the workspace authorisation
checks; `_backoff_seconds` implements the failure backoff.

## Gotchas

The registry probes the tool servers over HTTP, so a server that is down at
startup is absent until a successful refresh — the backoff is what keeps the
retry from hammering a dead server.
