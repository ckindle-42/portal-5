---
id: unit-HOWTO-discovery-with-fact-units
kind: why
title: Discovery with fact-units
sources:
- type: code
  path: portal_wiki/mcp.py
- type: code
  path: portal/platform/wiki/adapters/seed_facts.py
- type: code
  path: portal/platform/inference/sync_config.py
claims: []
confidence: high
tags:
- HOWTO
- discovery
- verified-v1
- wiki
created_at: 1784049570.60765
updated_at: 1784049570.60765
---

# Discovery with fact-units

Authored knowledge units under `portal_wiki/canonical/` are the source of
truth for durable guidance. Fact units (`unit-fact-*`) are computed on demand
by the wiki MCP from live config, code, and probes; their content is not stored
in the canonical directory. `sync-config` writes runtime artifacts only.
Generated docs are refreshed separately with `portal docs build` when needed.

## Order of operations
1. Use `wiki_search` / `wiki_explain` to find the relevant canonical unit.
2. Edit that unit for authored knowledge, or edit the governing config or code
   that supplies a computed fact.
3. Query `unit-fact-*` through `wiki_get_unit` or `wiki_search` for current
   computed values. Run `portal docs build` separately when generated docs need
   to be refreshed.
4. Treat `sources:` as provenance and navigation. They must resolve, but they do
   not reverse authority from the canonical unit back into a rendered document.

## Trust tiers
- **Fact-units** (`unit-fact-*`) — computed from governing config, code, and
  probes on each wiki MCP request; not persisted in the canonical store.
- **WHY / HOWTO units** — authored canonical intent and operating guidance.
- **Rendered documents** — projections only; direct edits are reserved for
  bounded human-owned fences and marker placement.

## The tool-reachability pair
- `unit-fact-tool-authorizations` — what each workspace exposes (the `tools:` whitelist).
- `unit-fact-tool-registry` — what each MCP server registers (`@mcp.tool()` defs).
A tool present in the registry but absent from a workspace's authorizations is a reachability gap;
a `!` in the authorizations unit is an authorized tool with no registry match (a bug).

## Why

Discovery is routed through fact units because their content is computed
from live config and code by `seed_facts.py` when `wiki_get_unit` or
`wiki_search` is called. The MCP overlays those computed units over authored
canonical units; no persisted fact snapshot or `sync-config` freshness gate is
involved. Start with the wiki tools to get the current derived view and its
sources, then inspect the governing files when implementation detail matters.
