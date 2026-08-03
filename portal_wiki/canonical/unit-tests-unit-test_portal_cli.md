---
id: unit-tests-unit-test_portal_cli
kind: mixed
title: "Unit tests \u2014 test_portal_cli"
sources:
- type: code
  path: tests/unit/test_portal_cli.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892294
updated_at: 1785800468.892294
---

Unit tests for test_portal_cli.

## Why

A CLI that cannot even print help is broken for every command, so the skeleton smoke test is the first gate. The commands resolving to their registered implementations is the minimal contract the CLI must satisfy.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
