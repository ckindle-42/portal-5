---
id: unit-capability-research
kind: mixed
title: "Research MCP \u2014 web search and fetch"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/research/tools/web_search_mcp.py
- type: code
  path: config/inference/tools_manifest_web_search_mcp.json
claims: []
confidence: high
tags:
- capability
- mcp
- research
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# Research MCP — web search and fetch

## What

The Research MCP (`portal/modules/research/tools/web_search_mcp.py`, port
8922) provides private web search, page fetch, and news search. It is
pipeline- and IDE-exposed and backs the `auto-research` workspace, running as
the `mcp-research` compose service with SearXNG as its backend.

## How it's used

`web_search` queries the local SearXNG instance, `web_fetch` retrieves a page's
content for grounding, and `news_search` returns current-news results. Because
the backend is the project's own SearXNG (port 8088), a search leaves the
machine only through the configured upstreams and carries no commercial search
API key.

## Why it exists

Research workspaces need a real, current web signal to ground answers, and the
platform's zero-cloud posture means that signal must come from a self-hosted
SearXNG rather than a paid search API. Keeping the tool surface on one MCP with
a bounded search/fetch vocabulary gives personas a controlled outbound path
that the telemetry layer can observe.

## Value

Answers in research and security workspaces cite live pages instead of relying
only on trained knowledge, all routed through a local search instance. The
single-tool vocabulary is easy to grant and easy to audit, and the default
posture requires no external account.
