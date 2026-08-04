---
id: unit-tests-unit-test_portal_yaml_consistency
kind: mixed
title: "Unit tests \u2014 test_portal_yaml_consistency"
sources:
- type: code
  path: tests/unit/test_portal_yaml_consistency.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892298
updated_at: 1785800468.892298
---

Unit tests for test_portal_yaml_consistency.

## Why

A workspace that references a model not in the catalog is a routing hole, and the cross-reference test catches it before a PR lands. Catching the drift at PR time is the difference between a clean deploy and a workspace that cannot serve.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
