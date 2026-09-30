---
id: unit-tests-unit-test_spine_gates
kind: mixed
title: Spine gate ratchet tests
sources:
- type: code
  path: tests/unit/test_spine_gates.py
  commit: d5234798
last_generated_commit: abe6f42ccd1cd1ce696800899e19dfc51821e0ef
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800427.158784
updated_at: 1785800427.158784
---

Ratchets the wiki and router spine correctness gates into the pytest CI lane.

## Why

The spine gates (AJ, AW, BR) are the wiki's correctness backbone, and ratcheting them into the pytest lane is what fails CI when they regress.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
