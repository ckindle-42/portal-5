---
id: unit-tests-unit-test_uat_dispatch_route_params
kind: mixed
title: "Unit tests \u2014 test_uat_dispatch_route_params"
sources:
- type: code
  path: tests/unit/test_uat_dispatch_route_params.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892352
updated_at: 1785800468.892352
---

Unit tests for test_uat_dispatch_route_params.

## Why

A dispatcher that drops route params would make the affected cases never execute the intended variation, and the test pins the forwarding. The route-params forwarding is the fix that made the cases actually run, so it is a regression guard.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
