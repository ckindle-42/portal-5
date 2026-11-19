---
id: unit-tests-unit-test_expected_models
historical: true
kind: mixed
title: "Unit tests \u2014 test_expected_models"
sources:
- type: code
  path: tests/unit/test_expected_models.py
  commit: d5234798
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit

---

Unit tests for test_expected_models.

## Why

The expected-model helper derives the routing ground truth from the config, and its tests verify the resolution. A helper that resolved the wrong expected model would make the routing checks fail on correct behaviour or pass on incorrect routing.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
