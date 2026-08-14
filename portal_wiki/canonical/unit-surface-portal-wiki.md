---
id: unit-surface-portal-wiki
kind: mixed
title: "portal_wiki package \u2014 agent retrieval and CLI maintenance surface"
sources:
- type: code
  path: portal_wiki/*.py
claims: []
confidence: high
tags:
- authored-v1
- wiki
created_at: 1785886000.0
updated_at: 1785886000.0
---

The `portal_wiki` package is the canonical knowledge layer's agent surface,
in three parts: a package entry that re-exports only the schema and store
primitives a script needs, a CLI maintenance surface, and pure retrieval
functions served as an HTTP MCP server to Open WebUI and other MCP clients.

## Why

The public surface stays small and stable so agents reach the spine through a
fixed contract. Retrieval logic stays in pure functions, testable without a
running MCP process; the server is a thin transport wiring them to the
fleet's HTTP shape. The keyword scorer is flat and deterministic — traceable
word matches ground better than fuzzy semantic ranking — and every answer
must carry its citations. Archive and re-ground preconditions are enforced in
the CLI, not left to operator discipline.

## Interfaces

The package entry re-exports `KnowledgeUnit`, `SourceRef`, `load_all`,
`load_unit`, and `save_unit`. The CLI offers `render` (view regeneration with
a `--check` drift gate), `status`, `drift`, `archive`, and `re-ground`. The
agent layer exposes `wiki_search`, `wiki_get_unit`, and `wiki_explain`; the
server (port 8931) mounts them as `@mcp.tool()` handlers alongside `/health`
and `/tools` routes backed by the single `TOOLS_MANIFEST` declaration.

## Gotchas

The port falls back from `WIKI_MCP_PORT` to `MCP_PORT` before 8931. The
scorer has no stemming, so `streaming` and `stream` score separately and a
single shared word can surface an unrelated unit. The CLI derives the repo
root from `__file__`, so it always targets this repository's canonical
directory.
