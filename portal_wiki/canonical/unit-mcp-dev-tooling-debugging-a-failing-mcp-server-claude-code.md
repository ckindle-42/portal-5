---
id: unit-mcp-dev-tooling-debugging-a-failing-mcp-server-claude-code
kind: what
title: "MCP_DEV_TOOLING \u2014 Debugging a failing MCP server (Claude Code)"
sources:
- type: code
  path: .mcp.json
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: portal/modules/coding/tools/code_sandbox_mcp.py
last_generated_commit: 9623f6b25b3e922bd0cf4b3885a926a4728b26a1
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.579058
updated_at: 1784946220.579058
---

When a Portal MCP tool errors, the containerised servers and the pipeline MCP expose
enough surface to diagnose without leaving Claude Code. The sandbox runs as the
`mcp-sandbox` compose service bound to :8914 (see `deploy/portal-5/docker-compose.yml`);
its logs and health endpoint answer the usual questions. The `filesystem`, `git`,
`docker`, and `fetch` servers in `.mcp.json` give the client container listing, log
reading, and an HTTP probe path, and the failing tool can be invoked directly to
reproduce the error. Health handlers like the one in `code_sandbox_mcp.py` report
sandbox posture at a glance.

## Why

MCP failure debugging is mostly localisation: is the container up, is the HTTP
endpoint answering, or is the tool's own logic throwing? The tool roster in
`.mcp.json` was assembled so each of those questions has a server to answer it,
turning a black-box tool failure into a short read of logs, health, and one direct
call.
