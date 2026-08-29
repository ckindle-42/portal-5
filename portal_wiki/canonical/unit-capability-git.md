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
claims: []
confidence: high
tags:
- capability
- mcp
- general
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# Git MCP — vendored IDE repository operations

## What

The Git MCP is the externally vendored `mcp-server-git` package, run via
`uvx` against the portal repository root (`${HOME}/projects/portal-5`). It is
declared in `config/portal.yaml`'s `mcp_fleet` under the `general` module and
is IDE-only (`expose_to_pipeline: false`, `expose_to_ide: true`).

## How it's used

The server exposes the git surface — status, diff, log, commit, branch, and
staging operations — scoped to the repository it is launched against. An IDE
agent inspects history and makes commits while working in the checked-out tree,
all without leaving the editor.

## Why it exists

Repository operations belong to the operator lane, so git joins the other three
vendored base tools under the same IDE-only boundary: a persona never gets a
commit or a history rewrite primitive. Portal ships it rather than writing a
thin wrapper because the third-party server already speaks MCP and the
complexity census expects a declared surface for it.

## Value

An agent can stage, diff, and commit as part of a review loop with the real git
state as ground truth, and the boundary keeps pipeline workspaces read-only with
respect to the repo — writing a commit is always an operator-authorized action.
