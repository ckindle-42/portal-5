---
id: unit-mcp-dev-tooling-fixing-a-bug-claude-code
kind: what
title: "MCP_DEV_TOOLING \u2014 Fixing a bug (Claude Code)"
sources:
- type: code
  path: portal/platform/mcp_host/pipeline_mcp.py
- type: code
  path: portal/platform/inference/router/routing.py
- type: code
  path: portal/platform/inference/router/workspaces.py
- type: code
  path: .mcp.json
last_generated_commit: 9623f6b25b3e922bd0cf4b3885a926a4728b26a1
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.578301
updated_at: 1784946220.578301
---

Fixing a routing bug with Claude Code in Portal mode follows the tool chain that
`.mcp.json` and the pipeline MCP provide. The session starts with
`explore_repository` to locate the routing and workspace-selection code, then reads
the exact ranges from `router/routing.py` or `router/workspaces.py`, makes the edit
through the filesystem server, verifies with `execute_bash` in the sandbox running
pytest, and finishes with the git server's diff and commit tools. Every step maps to
a concrete server in `.mcp.json`, so no manual checkout or terminal juggling is
required to take a fix from discovery to commit.

## Why

The walkthrough is really a contract between the tool roster and a debugging flow:
exploration, targeted read, edit, test, and version control are each owned by one
server. That separation keeps the expensive reasoning model focused on diagnosis
while the mechanical steps stay cheap and auditable, which is the whole point of
assembling the IDE tool set.
