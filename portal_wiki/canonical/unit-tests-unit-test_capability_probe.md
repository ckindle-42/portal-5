---
id: unit-tests-unit-test_capability_probe
kind: mixed
title: "Unit tests \u2014 test_capability_probe"
sources:
- type: code
  path: tests/unit/test_capability_probe.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.8922298
updated_at: 1785800468.8922298
---

Unit tests for test_capability_probe.

## Why

The probe's code-extraction and execution-scoring logic is verified hermetically, independent of any model. The execution-scoring basis is the whole point of the probe — code that runs and produces the expected output — and that logic must be correct before it is applied to any model's response.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
