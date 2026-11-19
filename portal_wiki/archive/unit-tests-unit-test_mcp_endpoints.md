---
id: unit-tests-unit-test_mcp_endpoints
historical: true
kind: mixed
title: "Unit tests \u2014 test_mcp_endpoints"
sources:
- type: code
  path: tests/unit/test_mcp_endpoints.py
  commit: d5234798
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit

---

Unit tests for test_mcp_endpoints.

## Why

The MCP servers expose an OpenAI-compatible shape for the fleet, and the tests verify those endpoints. A server whose OpenAI-compatible endpoint drifted from the shape the pipeline expects would break every tool call through that server.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
