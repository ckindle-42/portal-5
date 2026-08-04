---
id: unit-MCP_DEV_TOOLING-mcp-servers-mcp-json
kind: why
title: "MCP_DEV_TOOLING \u2014 MCP Servers (`.mcp.json`)"
sources:
- type: design
  path: docs/MCP_DEV_TOOLING.md
  section: MCP Servers (`.mcp.json`)
last_generated_commit: ''
confidence: high
tags:
- docs
- MCP_DEV_TOOLING
created_at: 1783195000.870443
updated_at: 1783195000.870443
---


Six servers activate when Claude Code or opencode opens this project:

| Server | Transport | Purpose |
|---|---|---|
| `filesystem` | npx `@modelcontextprotocol/server-filesystem` | Read/write/search repo source tree and `~/.portal5/logs` |
| `fetch` | uvx `mcp-fetch` | Read Prometheus metrics, pipeline `/health`, Ollama `/api/ps`, Grafana |
| `git` | uvx `mcp-server-git` | Commit, diff, log, blame — regression bisect and change tracking |
| `docker` | npx `@modelcontextprotocol/server-docker` | Container logs, status, exec — live MCP server debug |
| `portal-sandbox` | URL `:8914/mcp` | `execute_bash`, `execute_python`, `execute_nodejs` in isolated container |
| `portal-pipeline` | URL `:8928/mcp` | Stack introspection + FastContext repository explorer |
