---
id: unit-HOWTO-13-web-search
kind: why
title: "HOWTO \u2014 13. Web Search"
sources:
- type: code
  path: portal/modules/research/tools/web_search_mcp.py
- type: code
  path: config/searxng/settings.yml
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1783195000.850833
updated_at: 1783195000.850833
---

**What:** Web search via a self-hosted SearXNG instance.

**Activate:** Workspaces opt in with `enable_web_search: true` in `config/portal.yaml` (for example `auto-daily`, `auto-research`, `auto-compliance`); the model then sees `web_search` / `news_search` in its tool grant. `auto-research` even forces `tool_choice: required` because it once narrated a search without completing it.

**How:** The `web_search` tool lives in `portal/modules/research/tools/web_search_mcp.py` and queries the SearXNG container (port 8088) at `SEARXNG_URL`. SearXNG is self-hosted — no third-party AI provider sees queries — but the engines configured in `config/searxng/settings.yml` are public ones (google, duckduckgo, bing, github, stackoverflow), so query strings do reach those engines. If `BRAVE_API_KEY` is set, the tool switches to the Brave backend instead.

## Why

Self-hosting the aggregator keeps the search control plane (which engine, what formatting, what rate limits) under Portal's config rather than inside a model call, while the workspace-level `enable_web_search` flag keeps the capability out of lanes that do not need it. The privacy claim is accurate only about AI providers, which is why the engine list is the grounding for what actually leaves the host.
