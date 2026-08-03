---
id: unit-tests-unit-test_council_review
kind: mixed
title: "Unit tests \u2014 test_council_review"
sources:
- type: code
  path: tests/unit/test_council_review.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892255
updated_at: 1785800468.892255
---

Unit tests for test_council_review.

## Why

The council's seat isolation and quorum are the anti-groupthink design, and the tests pin them. A council where one seat's opinion leaked into another, or where a non-voter did not count against quorum, would rubber-stamp instead of genuinely cross-checking.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
