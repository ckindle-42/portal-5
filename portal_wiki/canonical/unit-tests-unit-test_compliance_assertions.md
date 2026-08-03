---
id: unit-tests-unit-test_compliance_assertions
kind: mixed
title: "Unit tests \u2014 test_compliance_assertions"
sources:
- type: code
  path: tests/unit/test_compliance_assertions.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892242
updated_at: 1785800468.892242
---

Unit tests for test_compliance_assertions.

## Why

The compliance assertions are the methodology checks, and their tests verify the pure functions hermetically. A methodology assertion that drifted would certify a compliance persona that no longer follows its mandated structure, so the pure functions are pinned without any network.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
