---
id: unit-sec-tests-test_drift_gate
kind: mixed
title: "Security tests \u2014 test_drift_gate"
sources:
- type: code
  path: portal/modules/security/tests/test_drift_gate.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986329
updated_at: 1785800599.986329
---

Unit tests for the security module's test_drift_gate surface.

## Why

Tests for the drift-detection gate, hermetically — the gate's metric math is pure. The drift metric must be correct before it gates anything, so the math is pinned in isolation.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
