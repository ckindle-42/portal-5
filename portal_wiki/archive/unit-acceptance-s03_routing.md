---
id: unit-acceptance-s03_routing
kind: mixed
title: "S3a \u2014 Workspace routing across all production workspaces"
sources:
- type: code
  path: tests/acceptance/s03_routing.py
  commit: a88ad75b
last_generated_commit: a88ad75b
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799717.531816
updated_at: 1785799717.531816
---

This is the acceptance section s03_routing. S3a — Workspace routing across all production workspaces

## Why

It exercises routing across the production workspace catalog (including the opt-in council review), proving every workspace resolves and serves. A workspace that routes wrong is caught here rather than surfacing as a section failure.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
