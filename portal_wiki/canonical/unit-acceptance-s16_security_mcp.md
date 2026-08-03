---
id: unit-acceptance-s16_security_mcp
kind: mixed
title: "S16 \u2014 Security MCP"
sources:
- type: code
  path: tests/acceptance/s16_security_mcp.py
  commit: a88ad75b
last_generated_commit: a88ad75b
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799790.1403499
updated_at: 1785799790.1403499
---

This is the acceptance section s16_security_mcp. S16 — Security MCP

## Why

It proves the security MCP servers answer and serve their tools. The security tool servers are standalone services, and a bridge that is down would make the security workspaces appear to lack their tool arsenal.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
