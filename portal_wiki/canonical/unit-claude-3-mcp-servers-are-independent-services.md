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
created_at: 1785348301.194331
updated_at: 1785348301.194331
---


Each MCP server (`portal/modules/*/tools/*_mcp.py`, `portal/platform/{mcp_host,memory}/`, or a vendored server in `portal_mcp/{filesystem,scrapling}/`) is a standalone service using the MCP SDK v2 `MCPServer` API (mounted in FastAPI where needed). They have zero imports from `portal.platform.inference` or `portal_channels/`. They are registered in Open WebUI as Tool Servers. They do not know about each other.
