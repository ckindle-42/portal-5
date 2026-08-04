---
id: unit-tests-unit-test_council_review_bench
kind: mixed
title: "Unit tests \u2014 test_council_review_bench"
sources:
- type: code
  path: tests/unit/test_council_review_bench.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892258
updated_at: 1785800468.892258
---

Unit tests for test_council_review_bench.

## Why

The bench's scoring must be deterministic so a verdict is reproducible, and the tests pin that determinism. A council verdict that depended on run order or a subtle nondeterminism could not be audited, so the scoring is locked down.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
