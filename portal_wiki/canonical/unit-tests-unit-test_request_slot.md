---
id: unit-tests-unit-test_request_slot
kind: mixed
title: "Unit tests \u2014 test_request_slot"
sources:
- type: code
  path: tests/unit/test_request_slot.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892318
updated_at: 1785800468.892318
---

Unit tests for test_request_slot.

## Why

A request slot that leaks a semaphore on an error path permanently degrades the pipeline, and the isolation tests pin the lifecycle. The single-owner lifecycle is what prevents the leak, and the tests prove it holds across success and failure paths.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
