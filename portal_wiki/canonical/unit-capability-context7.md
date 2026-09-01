---
id: unit-capability-context7
kind: mixed
title: "Context7 MCP — live version-accurate library documentation"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: opencode.jsonc
- type: code
  path: .mcp.json
claims: []
confidence: high
tags:
- capability
- mcp
- coding
---

# Context7 MCP — live version-accurate library documentation

## What

`portal-context7` (fleet id `context7`) is the upstream
`@upstash/context7-mcp` (Node) run locally under the existing `coding` module.
It is registered as an IDE-only stdio server — it appears in `.mcp.json` and
`opencode.jsonc` and is launched by the IDE's own MCP client (Claude Code /
opencode), not by the portal fleet bring-up. There is no Portal Python code
for it.

## How it's used

`resolve-library-id` maps a package/product name to a Context7 library id
(`/org/project`); `query-docs` returns current, version-specific documentation
and code examples for that id. A coding agent that would otherwise recall an
API from its training cutoff instead grounds against the library's real
current surface.

## Why it exists

The coding module has execution tools but no live library-docs grounding —
the antidote to a model confidently using an API that changed since its
cutoff. Running the upstream server locally keeps it self-hosted with no
Portal server to maintain; an optional `CONTEXT7_API_KEY` raises rate limits
but the public tier works without one.

## Value

Version-accurate docs on demand inside the IDE coding loop.

## Known gap

Not pipeline-exposed. Context7 v4 speaks only the MCP protocol at `/mcp`, not
the portal pipeline's REST `/tools` discovery/dispatch dialect, so the
OWUI-side `auto-coding` workspaces do not see `resolve-library-id` /
`query-docs` yet. Closing that would need a small REST shim — deliberately
out of scope for this config-only task (which was specified as "not a new
Python server").
