---
id: unit-HOWTO-discovery-with-fact-units
kind: why
title: Discovery with fact-units
sources:
- type: doc
  path: DESIGN_WIKI_TRUST_SLICE0_V1.md
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

Fact-units (`unit-fact-*`) are machine-derived from config and gated by validate check AW, so they
are trustworthy for **discovery/orientation** the moment AW is green. Use them first; do not re-derive
their content by hand.

## Order of operations
1. `wiki_search` / `wiki_explain` to find the relevant unit(s) and their `sources:` code paths.
2. Read the live file at HEAD for the exact edit anchor.
3. Verify every anchor `count==1` against HEAD before editing. Wiki points; HEAD proves.

## Trust tiers
- **Fact-units** (`kind: what`, `tags: [fact]`) — trusted index; AW keeps them honest.
- **WHY / HOWTO units** — trusted for intent and as pointers; verify specific claims at HEAD.

## The tool-reachability pair
- `unit-fact-tool-authorizations` — what each workspace exposes (the `tools:` whitelist).
- `unit-fact-tool-registry` — what each MCP server registers (`@mcp.tool()` defs).
A tool present in the registry but absent from a workspace's authorizations is a reachability gap;
a `!` in the authorizations unit is an authorized tool with no registry match (a bug).
