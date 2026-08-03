---
id: unit-tests-unit-test_portal_mitre_mcp
kind: mixed
title: "Unit tests \u2014 test_portal_mitre_mcp"
sources:
- type: code
  path: tests/unit/test_portal_mitre_mcp.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.8922958
updated_at: 1785800468.8922958
---

Unit tests for test_portal_mitre_mcp.

## Why

The MITRE MCP is the deterministic technique lookup, and its tests verify the lookup and the join to the local detections. A lookup that returned the wrong technique, or a join that missed a local detection, would mislead every agent that queries it.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
