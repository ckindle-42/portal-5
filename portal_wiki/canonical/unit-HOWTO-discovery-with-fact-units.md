---
id: unit-HOWTO-discovery-with-fact-units
kind: why
title: Discovery with fact-units
sources:
- type: doc
  path: docs/DESIGN_WIKI_GENERATION_LOOP_V1.md
last_generated_commit: ''
confidence: high
tags:
- HOWTO
- discovery
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
