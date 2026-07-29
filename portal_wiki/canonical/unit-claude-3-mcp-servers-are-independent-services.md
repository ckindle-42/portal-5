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


Each MCP server is a standalone service using the MCP SDK v2 `MCPServer` API,
mounted in FastAPI where needed. Servers do not import the inference platform or
channel adapters, are registered independently in Open WebUI, and do not depend
on one another.
