---
id: unit-tests-unit-test_uat_metrics_url
kind: mixed
title: "Unit tests \u2014 test_uat_metrics_url"
sources:
- type: code
  path: tests/unit/test_uat_metrics_url.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.8923578
updated_at: 1785800468.8923578
---

Unit tests for test_uat_metrics_url.

## Why

The metrics URL must resolve the same way as the config URLs, and the test pins the shared resolution. The same host-side resolution bug as the config module would make the metrics land in the wrong place.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
