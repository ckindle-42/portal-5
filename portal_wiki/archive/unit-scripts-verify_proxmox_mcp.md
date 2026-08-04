---
id: unit-scripts-verify_proxmox_mcp
kind: mixed
title: "Script \u2014 verify_proxmox_mcp"
sources:
- type: code
  path: scripts/verify_proxmox_mcp.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799583.725261
updated_at: 1785799583.725261
---

Runs without Docker, hitting the Proxmox API directly with the same client code as the MCP server, reading credentials from .env.

## Why

The Proxmox MCP's behaviour should be verifiable without the MCP server process, and the script reuses the server's own client code so what is verified is exactly what the server runs — the .env credential source is shared with the rest of the stack.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
