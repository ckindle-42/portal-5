---
id: unit-tests-unit-test_backend_registry_health
kind: mixed
title: "Unit tests \u2014 test_backend_registry_health"
sources:
- type: code
  path: tests/unit/test_backend_registry_health.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892214
updated_at: 1785800468.892214
---

Unit tests for test_backend_registry_health.

## Why

The backend registry's health semantics — hysteresis, clamping, and caching — are the operational details that determine routing under pressure. A registry that flapped between healthy and down, or served a stale cache, would route requests to a dead backend, so the tests pin these behaviours.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
