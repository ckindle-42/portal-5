---
id: unit-sec-tests-test_selfindex_fidelity
historical: true
kind: mixed
title: "Security tests \u2014 test_selfindex_fidelity"
sources:
- type: code
  path: portal/modules/security/tests/test_selfindex_fidelity.py
  commit: 862c7b11
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests

---

Unit tests for the security module's test_selfindex_fidelity surface.

## Why

Unit tests for the self-index fidelity fix, covering the two measurement bugs. The measurement bugs made the index report the wrong inventory, and the tests pin the fixes.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
