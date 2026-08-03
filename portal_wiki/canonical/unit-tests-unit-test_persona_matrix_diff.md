---
id: unit-tests-unit-test_persona_matrix_diff
kind: mixed
title: "Unit tests \u2014 test_persona_matrix_diff"
sources:
- type: code
  path: tests/unit/test_persona_matrix_diff.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892288
updated_at: 1785800468.892288
---

Unit tests for test_persona_matrix_diff.

## Why

The diff's regression/improvement classification is what gates a model promotion, and its tests verify the classification. A diff that misclassified a regression would let a worse model be promoted, so the classification is pinned.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
