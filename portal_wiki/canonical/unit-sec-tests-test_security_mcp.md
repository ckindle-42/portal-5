---
id: unit-sec-tests-test_security_mcp
kind: mixed
title: "Security tests \u2014 test_security_mcp"
sources:
- type: code
  path: portal/modules/security/tools/security_mcp.py
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.9864042
updated_at: 1785800599.9864042
---

The security MCP server. The in-tree suite that mocked torch and transformers to call it was removed in the phase-1c test trim.

## Why

The server is the tool surface for the security workspaces. A mocked torch import is not a contract the running system loads, and it does not pin a named live bug, so that offline suite was removed instead of being kept as evidence.

## Interfaces

`classify_vulnerability` and the native tool manifest live in `portal/modules/security/tools/security_mcp.py`.

## Gotchas

The deleted suite installed `sys.modules` mocks before import and could write through security runtime paths. The server creates journals only when a tool writes.
