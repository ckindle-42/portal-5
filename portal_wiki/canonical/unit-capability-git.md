---
id: unit-capability-git
kind: mixed
title: "Git MCP \u2014 vendored IDE repository operations"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/general/tools/__init__.py
- type: code
  path: portal/modules/orchestration/mcp/git_mcp.py
claims: []
confidence: high
tags:
- capability
- mcp
- orchestration
---

# Git MCP — IDE repository operations, plus a Pipeline surface that never touches the live checkout

## What

The Git fleet entry has two surfaces. IDE-side it is the externally vendored
`mcp-server-git` package, run via `uvx` against the portal repository root
(`${HOME}/projects/portal-5`) for operator repo work. Pipeline-side (J-R2) it
is the Portal host-native git MCP (:8950, `portal/modules/orchestration/mcp/
git_mcp.py`, launchd label `com.portal5.git-mcp`) — the entry is declared in
`config/portal.yaml`'s `mcp_fleet` under the `orchestration` module with
`expose_to_pipeline: true`.

## How it's used

The Pipeline surface serves `git_status`, `git_log`, `git_diff` (read-only,
open to Jarvis plans) and `git_commit`, `git_push` (confirm-gated by the
Jarvis personal policy). The server refuses the live Portal checkout it is
deployed from — Jarvis git work belongs in worktrees and other repos, and
that is a server-side guard, not a caller promise. Optional
`GIT_MCP_ALLOW_ROOT` narrows every call to one directory tree.

## Why it exists

The J-R2 gap: the fleet's git MCP had `expose_to_pipeline: true` but no port,
so the Pipeline never had a git endpoint. Upstream `mcp-server-git` could not
be reused for the Pipeline surface because its `--repository` restriction
cannot exclude a subdirectory of an allowed root and it has no push tool or
`/health` route — a Portal-native server enforces the live-checkout rule in
one place and follows the up-gate health convention.

## Value

Jarvis can answer "what changed in the worktree" and land a confirmed commit
in a non-live repo through the same tool loop as every other fleet tool,
while the IDE keeps the vendored server it already had.
