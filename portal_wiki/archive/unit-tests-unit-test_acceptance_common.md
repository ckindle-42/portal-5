---
id: unit-tests-unit-test_acceptance_common
historical: true
kind: mixed
title: Acceptance-common regression tests
sources:
- type: code
  path: tests/unit/test_acceptance_common.py
  commit: d5234798
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit

---

Regression tests for the acceptance harness request contract — the exact payload and routing the sections use.

## Why

A contract regression in the shared harness would fail every section at once, so the request-contract tests pin the harness shape before the section tests depend on it.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
