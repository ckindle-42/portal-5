---
id: unit-mcp-dev-tooling-install-if-missing
kind: what
title: "MCP_DEV_TOOLING \u2014 Install if missing:"
sources:
- type: code
  path: .mcp.json
- type: code
  path: launch.sh
last_generated_commit: 925f52c4b7e7ec876ea24823d3a221c7f2f8f505
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.571248
updated_at: 1784946220.571248
---

The four command-transport servers in `.mcp.json` — `filesystem`, `fetch`, `git`,
and `docker` — are launched via `npx` or `uvx`, so Node.js and uv must be installed
and on PATH before Claude Code or opencode can start them. The remote portal-*
servers have no such dependency: they are plain HTTP endpoints. The `portal-sandbox`
and `portal-pipeline` entries additionally require the stack to be running, because
`./launch.sh up` starts the sandbox container and the host-native pipeline MCP that
back them.

## Why

Splitting prerequisites between toolchain binaries and a live stack keeps the setup
diagnostic instead of magical. If an MCP server fails to load, the first question is
whether its transport depends on `npx` or `uvx` on PATH or on a service that only
exists after launch, and the answer is visible from how the server is declared in
`.mcp.json`.
