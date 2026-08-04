---
id: unit-mcp-host-core
kind: mixed
title: "mcp_host core \u2014 shared workspace path helpers"
sources:
- type: code
  path: portal/platform/mcp_host/__init__.py
  commit: ee7ca08a
last_generated_commit: ee7ca08a
claims: []
confidence: high
tags:
- authored-v1
- mcp
- platform
created_at: 1785795752.712359
updated_at: 1785795752.712359
---

The mcp_host package is the shared core for Portal 5's MCP servers: it holds
the workspace path helpers that every server needs to reach user files without
reimplementing the resolution logic. New MCPs are directed to these helpers
rather than hardcoding their own paths.

## Why

Path resolution has a container/host split — `$WORKSPACE_DIR` inside Docker,
`$AI_OUTPUT_DIR` on the host — and a future remap (mounting the workspace
somewhere else) should require no code changes beyond the env var. Centralising
the resolution in one helper package is what makes that remap cheap, and it
keeps every MCP's file access consistent with the shared-workspace rule (Rule
11 in CLAUDE.md): user files live at one root, never in container-local
volumes other services cannot see.

## Interfaces

The package re-exports `resolve_upload_path`, `get_uploads_dir`,
`get_generated_dir`, `get_workspace_root`, and `assert_public_http_url` from
`workspace.py` — the five helpers new MCPs are told to prefer.
