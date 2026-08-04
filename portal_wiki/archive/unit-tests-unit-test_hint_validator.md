---
id: unit-tests-unit-test_hint_validator
kind: mixed
title: "Unit tests \u2014 test_hint_validator"
sources:
- type: code
  path: tests/unit/test_hint_validator.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892267
updated_at: 1785800468.892267
---

Unit tests for test_hint_validator.

## Why

The hint validator is what rejects a bad workspace hint before it reaches the backend, and its tests pin the validation. A hint that passed validation but named a nonexistent workspace would be dispatched to a route that cannot serve it.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
