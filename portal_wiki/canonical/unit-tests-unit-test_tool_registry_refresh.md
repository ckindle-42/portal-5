---
id: unit-tests-unit-test_tool_registry_refresh
kind: mixed
title: "Unit tests \u2014 test_tool_registry_refresh"
sources:
- type: code
  path: tests/unit/test_tool_registry_refresh.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892342
updated_at: 1785800468.892342
---

Unit tests for test_tool_registry_refresh.

## Why

A refresh that drops or carries forward the wrong tool definitions breaks dispatch, and the tests pin the refresh semantics. The carry-forward behaviour — what survives a refresh when a server is briefly down — is exactly what these tests lock down.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
