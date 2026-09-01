---
id: unit-capability-wiki
kind: mixed
title: "Wiki MCP \u2014 canonical knowledge layer"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal_wiki/wiki_mcp.py
- type: code
  path: scripts/native-mcp-service.sh
claims:
- probe: wiki.canonical.units
  pattern: '{value} canonical units'
confidence: high
tags:
- capability
- mcp
- platform
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# Wiki MCP — canonical knowledge layer

## What

The Wiki MCP (`portal_wiki/wiki_mcp.py`, port 8931) is a host-native service
that serves the canonical knowledge layer in `portal_wiki/canonical/` — 717 canonical units. It is pipeline- and IDE-exposed and is the discovery index
the whole documentation system is built on.

## How it's used

`wiki_search` finds units by keyword, `wiki_get_unit` returns a unit's full
content by id, and `wiki_explain` answers a question by searching the canonical
layer and returning a cited answer. Reads use a repo-relative path to
`portal_wiki/canonical/` and `wiki_explain` calls Ollama directly for the
synthesis — which is why the service runs host-native rather than inside the
mcp Docker image.

## Why it exists

The wiki is source-of-truth knowledge: before grepping, an agent queries it
(`wiki_search` / `wiki_get_unit` / `wiki_explain`), so answers cite their unit
instead of being cold-grepped. Serving it as an MCP is what makes that
discipline available to any connected agent in the same typed, deterministic
way the facts were authored.

## Value

Every answer carries a citation back to a canonical unit, so an agent's
reasoning is checkable against the same source the docs render from. It turns
"lead discovery from the wiki" from a convention into a callable tool, keeping
architecture rationale and technique signatures one lookup away.
