---
id: unit-scripts-update_workspace_tools
kind: mixed
title: "Script \u2014 update_workspace_tools"
sources:
- type: code
  path: scripts/update_workspace_tools.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799576.324074
updated_at: 1785799576.324074
---

Regenerates the workspace tool-authorization entries from the tool registry, keyed by top-level workspace id.

## Why

The workspace tool authorizations must track the tool registry, and the regenerator is what keeps the derived authorization file in sync with the registry it describes.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
