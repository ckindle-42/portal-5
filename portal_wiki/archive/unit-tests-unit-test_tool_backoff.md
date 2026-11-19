---
id: unit-tests-unit-test_tool_backoff
historical: true
kind: mixed
title: "Unit tests \u2014 test_tool_backoff"
sources:
- type: code
  path: tests/unit/test_tool_backoff.py
  commit: d5234798
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit

---

Unit tests for test_tool_backoff.

## Why

The backoff is what keeps the registry from hammering a dead tool server, and the tests pin the exponential schedule. A backoff that fired too fast would flood a dead server, and one that was too slow would delay dispatch to a recovered one.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
