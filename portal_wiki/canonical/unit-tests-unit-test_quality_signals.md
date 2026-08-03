---
id: unit-tests-unit-test_quality_signals
kind: mixed
title: "Unit tests \u2014 test_quality_signals"
sources:
- type: code
  path: tests/unit/test_quality_signals.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.89231
updated_at: 1785800468.89231
---

Unit tests for test_quality_signals.

## Why

A quality verifier that rejects a correct-but-differently-worded answer is wrong, and these tests prove the fix for that. The verifier's job is to judge quality, not exact phrasing, so the correct-but-different case is the regression guard.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
