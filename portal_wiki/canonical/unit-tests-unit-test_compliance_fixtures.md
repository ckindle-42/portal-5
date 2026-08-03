---
id: unit-tests-unit-test_compliance_fixtures
kind: mixed
title: "Unit tests \u2014 test_compliance_fixtures"
sources:
- type: code
  path: tests/unit/test_compliance_fixtures.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892245
updated_at: 1785800468.892245
---

Unit tests for test_compliance_fixtures.

## Why

The fixture loader turns the YAML into concrete scenario tuples, and the tests verify the transform. A fixture that failed to expand would silently drop scenarios from the matrix, so the loading is verified.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
