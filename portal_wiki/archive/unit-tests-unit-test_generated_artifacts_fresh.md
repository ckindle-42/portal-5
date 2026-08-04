---
id: unit-tests-unit-test_generated_artifacts_fresh
kind: mixed
title: "Unit tests \u2014 test_generated_artifacts_fresh"
sources:
- type: code
  path: tests/unit/test_generated_artifacts_fresh.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.8922648
updated_at: 1785800468.8922648
---

Unit tests for test_generated_artifacts_fresh.

## Why

Idempotence is the load-bearing property of the single-source rule, and these tests assert that running sync-config twice changes nothing. A generator that produced a diff on re-run would mean a hand-edit slipped in, which is exactly the drift the freshness gate exists to catch.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
