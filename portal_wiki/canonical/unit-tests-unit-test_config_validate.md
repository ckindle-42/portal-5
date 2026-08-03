---
id: unit-tests-unit-test_config_validate
kind: mixed
title: "Unit tests \u2014 test_config_validate"
sources:
- type: code
  path: tests/unit/test_config_validate.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892253
updated_at: 1785800468.892253
---

Unit tests for test_config_validate.

## Why

The pre-gate catches config invariants before regeneration corrupts derived artifacts, and its tests pin the invariant checks. The validator is the fast dependency-light gate on the sync hot path, so its checks must be exactly the ones that matter to the generators.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
