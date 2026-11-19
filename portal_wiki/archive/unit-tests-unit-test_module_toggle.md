---
id: unit-tests-unit-test_module_toggle
historical: true
kind: mixed
title: "Unit tests \u2014 test_module_toggle"
sources:
- type: code
  path: tests/unit/test_module_toggle.py
  commit: d5234798
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit

---

Unit tests for test_module_toggle.

## Why

The toggle is the routing control for a module's workspaces, and the tests pin the enable/disable semantics. A toggle that hid the wrong workspaces, or left them routable after disable, would break the module boundary the toggle exists to enforce.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
