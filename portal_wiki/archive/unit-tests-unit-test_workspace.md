---
id: unit-tests-unit-test_workspace
kind: mixed
title: "Unit tests \u2014 test_workspace"
sources:
- type: code
  path: tests/unit/test_workspace.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.8923688
updated_at: 1785800468.8923688
---

Unit tests for test_workspace.

## Why

The workspace path resolution is the shared-workspace contract, and its tests verify the resolution and the traversal guard. A traversal hole in an upload path would be an arbitrary file read, and a wrong root would strand generated artifacts.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
