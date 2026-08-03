---
id: unit-tests-unit-conftest
kind: mixed
title: Unit-test conftest
sources:
- type: code
  path: tests/unit/conftest.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800427.158655
updated_at: 1785800427.158655
---

Unit-test-specific pytest configuration that ensures the prometheus client can initialize on the platform Python version.

## Why

Prometheus multiprocess mode and collector registration are version-sensitive, and a conftest that makes them initialise is what keeps the metrics-touching unit tests green across platform versions.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
