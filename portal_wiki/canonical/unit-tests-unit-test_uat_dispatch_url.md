---
id: unit-tests-unit-test_uat_dispatch_url
kind: mixed
title: "Unit tests \u2014 test_uat_dispatch_url"
sources:
- type: code
  path: tests/unit/test_uat_dispatch_url.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892354
updated_at: 1785800468.892354
---

Unit tests for test_uat_dispatch_url.

## Why

A URL-resolution bug that silently skipped cases was the failure, and the test pins the corrected resolution. The never-executed cases were the symptom — the URL resolution is the cause, and the test locks the fix.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
