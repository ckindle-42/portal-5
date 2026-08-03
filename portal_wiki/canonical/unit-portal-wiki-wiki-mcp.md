---
id: unit-portal-wiki-wiki-mcp
kind: mixed
title: "Wiki MCP server \u2014 HTTP transport for agent retrieval"
sources:
- type: code
  path: portal_wiki/wiki_mcp.py
  commit: dc13b2d5
last_generated_commit: dc13b2d5
claims: []
confidence: high
tags:
- authored-v1
- wiki
- mcp
created_at: 1785796122.622566
updated_at: 1785796122.622566
---

`wiki_mcp.py` is the HTTP MCP server (port 8931) that exposes the wiki's
agent retrieval to Open WebUI and any MCP client: `wiki_search`,
`wiki_get_unit`, and `wiki_explain` as served tools. It is a thin transport —
the implementations are the pure functions in `portal_wiki/mcp.py`, and this
module's real job is wiring them to the server and pointing the store at the
canonical directory.

## Why

The wiki retrieval logic is deliberately kept out of the server module so it
can be imported and tested without a running MCP process, and the server in
turn is what makes the same tools available over the fleet's HTTP shape. The
`_ensure_canonical` call before every tool invocation is the guard that a
server started outside the repo still finds the canonical tree: it sets the
store's canonical dir from the package location rather than assuming a cwd.
`wiki_explain`'s instructions to the client ("every answer cites its source")
encode the grounding contract into the tool description itself.

## Interfaces

The three `@mcp.tool()` functions mirror the pure functions, each calling
`_ensure_canonical` then delegating. `/health` and `/tools` are the fleet
convention endpoints. The manifest is declared once as `TOOLS_MANIFEST` so
the `/tools` route and the MCP tool registrations describe the same surface.

## Gotchas

The port reads `WIKI_MCP_PORT` with a fallback to `MCP_PORT` before the
default 8931 — the two-env-var fallback exists because the fleet once used a
shared `MCP_PORT` convention.
