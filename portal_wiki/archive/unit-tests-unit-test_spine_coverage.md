---
id: unit-tests-unit-test_spine_coverage
kind: mixed
title: "Unit tests \u2014 test_spine_coverage"
sources:
- type: code
  path: tests/unit/test_spine_coverage.py
  commit: 3e884375
last_generated_commit: 6afb262648d307376dfb4f839eeed69c02112d04
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.8923311
updated_at: 1785800468.8923311
---

Unit tests for test_spine_coverage.

## Why

A coverage gate that only works on one repo state is not a gate, so the tests exercise it on synthetic trees. The hermetic design proves the gate's semantics independently of the live repository's current shape.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
