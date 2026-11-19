---
id: unit-acceptance-s16_security_mcp
historical: true
kind: mixed
title: "S16 \u2014 Security MCP"
sources:
- type: code
  path: tests/acceptance/s16_security_mcp.py
  commit: e75dddd2
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance

---

This is the acceptance section s16_security_mcp. S16 — Security MCP

## Why

It proves the security MCP servers answer and serve their tools. The security tool servers are standalone services, and a bridge that is down would make the security workspaces appear to lack their tool arsenal.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
