---
id: unit-tests-unit-test_provenance_ledger
kind: mixed
title: "Unit tests \u2014 test_provenance_ledger"
sources:
- type: code
  path: tests/unit/test_provenance_ledger.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892305
updated_at: 1785800468.892305
---

Unit tests for test_provenance_ledger.

## Why

The provenance ledger is the commit-recorded derivation history, and its tests verify the operations. A ledger that recorded the wrong commit would make a derived unit's provenance a lie, defeating the audit trail it exists to provide.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
