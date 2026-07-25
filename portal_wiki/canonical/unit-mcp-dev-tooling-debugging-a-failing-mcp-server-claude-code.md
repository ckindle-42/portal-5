---
id: unit-mcp-dev-tooling-debugging-a-failing-mcp-server-claude-code
kind: what
title: "MCP_DEV_TOOLING \u2014 Debugging a failing MCP server (Claude Code)"
sources:
- type: doc
  path: docs/MCP_DEV_TOOLING.md
  commit: 05e42ec2
  section: Debugging a failing MCP server (Claude Code)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.579058
updated_at: 1784946220.579058
---

```
You: "portal-sandbox is returning errors on execute_bash"

Claude Code:
  docker/list_containers → confirms portal5-mcp-sandbox is Up
  docker/container_logs portal5-mcp-sandbox → finds the traceback
  fetch/fetch http://localhost:8914/health → reads health state
  portal-sandbox/execute_bash "ls /workspace" → tests the tool directly
```
