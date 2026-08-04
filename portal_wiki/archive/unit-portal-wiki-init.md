---
id: unit-portal-wiki-init
kind: mixed
title: "portal_wiki package \u2014 knowledge-layer entry surface"
sources:
- type: code
  path: portal_wiki/__init__.py
  commit: dc13b2d5
last_generated_commit: dc13b2d5
claims: []
confidence: high
tags:
- authored-v1
- wiki
created_at: 1785796105.492609
updated_at: 1785796105.492609
---

The `portal_wiki` package is the agent-facing entry to the canonical
knowledge layer: a thin re-export of the schema and store primitives an agent
or script needs to load, read, and save knowledge units.

## Why

The package exists so the wiki's public surface is small and stable. Agents
query the spine through `wiki_search`/`wiki_get_unit`/`wiki_explain`; code
that must read or write units directly gets the three store operations from
here rather than importing `portal.platform.wiki.store` internals. The
re-export is deliberately minimal — it is the load path, not a general API.

## Interfaces

`KnowledgeUnit` and `SourceRef` are the schema types; `load_all`,
`load_unit`, and `save_unit` are the store operations. Everything else lives
in the sibling modules (`mcp`, `__main__`) or under `portal.platform.wiki`.
