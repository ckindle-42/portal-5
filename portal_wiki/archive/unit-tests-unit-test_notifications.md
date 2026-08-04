---
id: unit-tests-unit-test_notifications
kind: mixed
title: "Unit tests \u2014 test_notifications"
sources:
- type: code
  path: tests/unit/test_notifications.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892284
updated_at: 1785800468.892284
---

Unit tests for test_notifications.

## Why

The notification fan-out and threshold logic is verified with no network, pinning the dispatcher contract. A dispatcher that misfired on a threshold or dropped a channel would leave an operator unaware of a backend-down condition.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
