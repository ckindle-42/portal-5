---
id: unit-tests-unit-test_acceptance_common
kind: mixed
title: Acceptance-common regression tests
sources:
- type: code
  path: tests/unit/test_acceptance_common.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800427.158659
updated_at: 1785800427.158659
---

Regression tests for the acceptance harness request contract — the exact payload and routing the sections use.

## Why

A contract regression in the shared harness would fail every section at once, so the request-contract tests pin the harness shape before the section tests depend on it.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
