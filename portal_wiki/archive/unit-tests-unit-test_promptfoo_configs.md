---
id: unit-tests-unit-test_promptfoo_configs
kind: mixed
title: "Unit tests \u2014 test_promptfoo_configs"
sources:
- type: code
  path: tests/unit/test_promptfoo_configs.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892303
updated_at: 1785800468.892303
---

Unit tests for test_promptfoo_configs.

## Why

A promptfoo config pointing at a non-existent model silently tests nothing, and the validation is the guard. The config would report pass on a model that does not exist, which is a false signal worse than no signal.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
