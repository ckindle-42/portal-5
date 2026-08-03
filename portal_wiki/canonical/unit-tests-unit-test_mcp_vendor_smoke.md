---
id: unit-tests-unit-test_mcp_vendor_smoke
kind: mixed
title: "Unit tests \u2014 test_mcp_vendor_smoke"
sources:
- type: code
  path: tests/unit/test_mcp_vendor_smoke.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.8922749
updated_at: 1785800468.8922749
---

Unit tests for test_mcp_vendor_smoke.

## Why

A de-vendoring that breaks an import path breaks the server at startup, and the smoke test catches it at import time. Import-time is the cheapest place to catch it — a server that fails to import never even reaches its health check.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
