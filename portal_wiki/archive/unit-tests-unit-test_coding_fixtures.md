---
id: unit-tests-unit-test_coding_fixtures
kind: mixed
title: "Unit tests \u2014 test_coding_fixtures"
sources:
- type: code
  path: tests/unit/test_coding_fixtures.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.8922398
updated_at: 1785800468.8922398
---

Unit tests for test_coding_fixtures.

## Why

The fixture loader is the transform over the scenario YAML, and its tests verify the loading and parameterisation. A loader that mis-expanded a scenario would make the matrix driver run the wrong assertions, so the transform is verified.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
