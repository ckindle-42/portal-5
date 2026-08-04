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
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
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

The canonical units under `portal_wiki/canonical/` are the source of truth.
Fact-units (`unit-fact-*`) are the machine-derived subset: `sync-config`
refreshes them from live configuration and validate check AW prevents their
generated projections from drifting. Other canonical units are intentionally
authored in the spine and then rendered into the documents that humans read.

## Order of operations
1. Use `wiki_search` / `wiki_explain` to find the relevant canonical unit.
2. Edit that unit for authored knowledge, or edit the governing config/code for
   a machine-derived fact-unit.
3. Run `sync-config` so fact-units refresh and all managed document blocks are
   regenerated.
4. Treat `sources:` as provenance and navigation. They must resolve, but they do
   not reverse authority from the canonical unit back into a rendered document.

## Trust tiers
- **Fact-units** (`kind: what`, `tags: [fact]`) — generated from governing
  config/code and checked by AW.
- **WHY / HOWTO units** — authored canonical intent and operating guidance.
- **Rendered documents** — projections only; direct edits are reserved for
  bounded human-owned fences and marker placement.

## The tool-reachability pair
- `unit-fact-tool-authorizations` — what each workspace exposes (the `tools:` whitelist).
- `unit-fact-tool-registry` — what each MCP server registers (`@mcp.tool()` defs).
A tool present in the registry but absent from a workspace's authorizations is a reachability gap;
a `!` in the authorizations unit is an authorized tool with no registry match (a bug).

## Why

Discovery is routed through fact-units because they are the only units
whose content is mechanically regenerated from live config rather than
authored: `seed_facts.py` derives each `unit-fact-*` body from
`config/portal.yaml` and `config/backends.yaml`, `sync-config` re-runs the
seeder, and validate check AW diffs each fact-unit against live config so
a drifted catalog cannot hide. The `wiki_search`/`wiki_explain` tools in
`portal_wiki/mcp.py` search this store, which is why the "order of
operations" starts with the search tools rather than with a grep: an
answer found through the fact-units is current, cited, and re-derivable,
where a claim read cold from source may describe a config that has since
moved.
