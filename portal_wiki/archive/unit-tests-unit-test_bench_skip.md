---
id: unit-tests-unit-test_bench_skip
kind: mixed
title: "Unit tests \u2014 test_bench_skip"
sources:
- type: code
  path: tests/unit/test_bench_skip.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892222
updated_at: 1785800468.892222
---

Unit tests for test_bench_skip.

## Why

The skip list is the operator's control over which workspaces the bench skips, and its tests pin the skip semantics. A skip rule that fired too eagerly would silently hide workspaces from the bench, and one that never fired would waste hours on workspaces the operator meant to exclude.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
