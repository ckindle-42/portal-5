---
id: unit-tests-unit-test_sandbox_network_flag
kind: mixed
title: "Unit tests \u2014 test_sandbox_network_flag"
sources:
- type: code
  path: tests/unit/test_sandbox_network_flag.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.8923259
updated_at: 1785800468.8923259
---

Unit tests for test_sandbox_network_flag.

## Why

The default-off posture is the sandbox's safety boundary, and the tests pin that the source only widens with the explicit flag. A sandbox that gained network access by default would break the isolation contract every persona depends on.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
