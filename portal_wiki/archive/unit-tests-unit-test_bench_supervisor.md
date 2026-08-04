---
id: unit-tests-unit-test_bench_supervisor
kind: mixed
title: "Unit tests \u2014 test_bench_supervisor"
sources:
- type: code
  path: tests/unit/test_bench_supervisor.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892224
updated_at: 1785800468.892224
---

Unit tests for test_bench_supervisor.

## Why

The supervisor's corrective actions must be verified without a live bench, so the tests mock the subprocess and the primitives to pin the failure-detection logic. A supervisor that misidentified a failure mode would take the wrong corrective action against a real bench run, which is why the detection logic is tested in isolation.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
