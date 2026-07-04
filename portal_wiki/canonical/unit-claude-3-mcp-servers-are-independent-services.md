---
id: unit-claude-3-mcp-servers-are-independent-services
kind: why
title: "CLAUDE.md \u2014 3 \u2014 MCP Servers Are Independent Services"
sources:
- type: design
  path: CLAUDE.md
  section: "3 \u2014 MCP Servers Are Independent Services"
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1783195000.806709
updated_at: 1783195000.806709
---


Each `portal_mcp/` server is a standalone FastAPI+FastMCP app. They have zero imports from `portal_pipeline/` or `portal_channels/`. They are registered in Open WebUI as Tool Servers. They do not know about each other.
