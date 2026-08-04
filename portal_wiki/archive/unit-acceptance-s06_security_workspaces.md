---
id: unit-acceptance-s06_security_workspaces
kind: mixed
title: "S6 \u2014 Security workspace tests"
sources:
- type: code
  path: tests/acceptance/s06_security_workspaces.py
  commit: a88ad75b
last_generated_commit: a88ad75b
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799756.6338198
updated_at: 1785799756.6338198
---

This is the acceptance section s06_security_workspaces. S6 — Security workspace tests

## Why

It exercises the security workspaces and their tool authorizations, proving the security tier routes, serves, and carries its tool set. The security workspaces are the most tool-dependent in the fleet, so their section is where a tool-authorization regression surfaces first.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
