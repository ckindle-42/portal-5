---
id: unit-scripts-migrate_to_portal_yaml
kind: mixed
title: "Script \u2014 migrate_to_portal_yaml"
sources:
- type: code
  path: scripts/migrate_to_portal_yaml.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799532.379113
updated_at: 1785799532.379113
---

Migrates the workspace and MCP server definitions from the code literals and .mcp.json into config/portal.yaml, the single source of truth.

## Why

Rule 6 makes portal.yaml the source of truth, and a migration that moves the literal definitions there is the mechanical step that ends the dual-source state where the code and the config could disagree.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
