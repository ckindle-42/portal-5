---
id: unit-sec-tests-test_security_mcp
kind: mixed
title: "Security tests \u2014 test_security_mcp"
sources:
- type: code
  path: portal/modules/security/tests/test_security_mcp.py
  commit: bdbf509f
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

Unit tests for the security module's test_security_mcp surface.

## Why

Unit tests for the security MCP server. The MCP server is the tool surface for the security workspaces, and its tests verify the server contract.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
