---
id: unit-mcp-dev-tooling-prerequisites
kind: what
title: "MCP_DEV_TOOLING \u2014 Prerequisites"
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
created_at: 1784946220.570942
updated_at: 1784946220.570942
---

The four command-transport servers in `.mcp.json` (`filesystem`, `fetch`, `git`,
`docker`) are spawned through `npx` or `uvx`, so those two runners must be on PATH.
`npx` ships with Node.js, and `uvx` ships with uv — both are single-install tools.
The remote portal-* servers need nothing beyond a running stack, and the 
`portal-sandbox` and `portal-pipeline` entries specifically require `./launch.sh up`
to have brought up the sandbox container and the host-native pipeline MCP.

## Why

Prerequisites are worth stating as a list because the failure they prevent is silent:
an MCP server that fails to spawn because `uvx` is missing looks exactly like a
server that crashed. Naming the two runners and the one stack command up front turns
that ambiguity into a two-minute check instead of a debugging session.
