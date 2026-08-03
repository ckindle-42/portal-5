---
id: unit-tests-unit-test_uat_grading
kind: mixed
title: "Unit tests \u2014 test_uat_grading"
sources:
- type: code
  path: tests/unit/test_uat_grading.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.8923562
updated_at: 1785800468.8923562
---

Unit tests for test_uat_grading.

## Why

A grading bug that inverted criticality would report the opposite of reality, and the regression test pins the correct grading. The inverted-critical bug is exactly the kind of failure that looks fine in aggregate and is wrong per case.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
