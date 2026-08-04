---
id: unit-MCP_DEV_TOOLING-debugging-a-failing-mcp-server-claude-code
kind: why
title: "MCP_DEV_TOOLING \u2014 Debugging a failing MCP server (Claude Code)"
sources:
- type: design
  path: docs/MCP_DEV_TOOLING.md
  section: Debugging a failing MCP server (Claude Code)
last_generated_commit: ''
confidence: high
tags:
- docs
- MCP_DEV_TOOLING
created_at: 1783195000.874463
updated_at: 1783195000.874463
---


```
You: "portal-sandbox is returning errors on execute_bash"

Claude Code:
  docker/list_containers → confirms portal5-mcp-sandbox is Up
  docker/container_logs portal5-mcp-sandbox → finds the traceback
  fetch/fetch http://localhost:8914/health → reads health state
  portal-sandbox/execute_bash "ls /workspace" → tests the tool directly
```
