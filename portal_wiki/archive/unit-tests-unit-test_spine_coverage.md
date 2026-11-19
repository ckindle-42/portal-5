---
id: unit-tests-unit-test_spine_coverage
historical: true
kind: mixed
title: "Unit tests \u2014 test_spine_coverage"
sources:
- type: code
  path: tests/unit/test_spine_coverage.py
  commit: d5234798
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit

---

Unit tests for test_spine_coverage.

## Why

A coverage gate that only works on one repo state is not a gate, so the tests exercise it on synthetic trees. The hermetic design proves the gate's semantics independently of the live repository's current shape.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
