---
id: unit-module-research
kind: mixed
title: "Research Module \u2014 web search, RAG, browser automation"
sources:
- type: code
  path: portal/modules/research/tools/web_search_mcp.py
- type: code
  path: portal/modules/research/tools/rag_mcp.py
- type: code
  path: portal/platform/wiki/adapters/modules.py
- type: code
  path: config/portal.yaml
claims:
- probe: modules.enabled
  contains: research
confidence: high
tags:
- module
- research
- verified-v1
created_at: 1783821386.790582
updated_at: 1783821386.790582
---

# Research Module — web search, RAG, browser automation

## Tools

`portal.modules.research.tools`: `web_search_mcp` (:8922, SearXNG),
`rag_mcp` (:8921), `reranker_mcp` (:8925), `browser_mcp` (:8923,
Obscura) — all registered under the `research` module in
`config/portal.yaml` `mcp_fleet:`.

## Workspaces

- `auto-research` — research assistant
- `auto-data` — data analysis

`browser_mcp` is assigned here (not its own module) — web automation
supports research, per operator best-fit direction.

## Module State

```yaml
enabled: true
```

## Why

The research module owns four fleet ids and two workspaces, so its toggle
controls both routing and tool availability in one move, read from the
fenced `enabled:` field by `portal/platform/wiki/adapters/modules.py`
(`_unit_enabled_state`). Two of its servers (`reranker`, `browser`) are
not pipeline-exposed, which means the module's real reachable surface is
narrower than its fleet count suggests. This unit is sourced to the
adapter that reads the toggle, the `portal/modules/research/tools/`
package that implements the servers, and `config/portal.yaml` that
declares their ports and exposure flags.
