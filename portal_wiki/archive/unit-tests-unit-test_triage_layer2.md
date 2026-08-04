---
id: unit-tests-unit-test_triage_layer2
kind: mixed
title: "Unit tests \u2014 test_triage_layer2"
sources:
- type: code
  path: tests/unit/test_triage_layer2.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.8923469
updated_at: 1785800468.8923469
---

Unit tests for test_triage_layer2.

## Why

The layer-2 triage maps failure context to a fixed action menu, and the tests verify that without a live model. A triage that mapped to an out-of-menu action, or to no action, would leave the supervisor unable to respond.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
