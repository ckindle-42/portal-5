---
id: unit-tests-unit-test_recall_scorer
kind: mixed
title: "Unit tests \u2014 test_recall_scorer"
sources:
- type: code
  path: tests/unit/test_recall_scorer.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892315
updated_at: 1785800468.892315
---

Unit tests for test_recall_scorer.

## Why

The LCS-based recall scorer is verified deterministically, proving the line-alignment logic without a model. The scoring must be correct before any model output is scored with it, so the deterministic logic is tested in isolation.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
