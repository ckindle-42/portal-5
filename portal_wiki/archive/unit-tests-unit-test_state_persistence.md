---
id: unit-tests-unit-test_state_persistence
historical: true
kind: mixed
title: "Unit tests \u2014 test_state_persistence"
sources:
- type: code
  path: tests/unit/test_state_persistence.py
  commit: d5234798
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit

---

Unit tests for test_state_persistence.

## Why

The metrics-state persistence must handle concurrent workers without losing deltas, and the tests verify that. With multiple uvicorn workers each saving state, a delta that got overwritten would lose telemetry the dashboards depend on.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
