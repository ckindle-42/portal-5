---
id: unit-tests-unit-test_bench_capability_cli
historical: true
kind: mixed
title: "Unit tests \u2014 test_bench_capability_cli"
sources:
- type: code
  path: tests/unit/test_bench_capability_cli.py
  commit: d5234798
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit

---

Unit tests for test_bench_capability_cli.

## Why

The capability bench CLI is the operator surface for fleet-mode capability runs, and its tests verify the invocation and output contract. A CLI that accepted the wrong flags or returned results in the wrong shape would make every capability run unreliable, so the contract is pinned.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
