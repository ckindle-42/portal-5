---
id: unit-capability-fetch
kind: mixed
title: "Fetch MCP \u2014 vendored IDE web fetch"
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

# Fetch MCP — vendored IDE web fetch

## What

The Fetch MCP is the externally vendored `mcp-fetch` package (pinned via
`uvx --with mcp<2.0.0`), declared in `config/portal.yaml`'s `mcp_fleet` under
the `general` module. It is IDE-only (`expose_to_pipeline: false`,
`expose_to_ide: true`), rendered to `.mcp.json` by `sync-config`.

## How it's used

The server turns a URL into a readable page or artifact for the agent: fetch a
document, follow the returned content, and pass it into the working context.
An IDE agent calls it to bring external pages into a conversation without
leaving the editor.

## Why it exists

Fetch is one of the four base tools the general module treats as
infrastructure rather than product: it is a vendored third-party server with no
Portal implementation. Keeping it IDE-only follows the same rule as the rest of
the base fleet — an arbitrary outbound fetch is fine when a human operator
requests it, and out of scope for a persona's autonomous tool loop.

## Value

Repository work that needs a referenced page — an upstream issue, a spec, a
release note — resolves inline instead of forcing a copy-paste, while the
pipeline's own bounded web search and fetch tools remain the persona-facing
path with their own controls.
