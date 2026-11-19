---
id: unit-sec-tests-test_matrix
historical: true
kind: mixed
title: "Security tests \u2014 test_matrix"
sources:
- type: code
  path: portal/modules/security/tests/test_matrix.py
  commit: 862c7b11
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests

---

Unit tests for the security module's test_matrix surface.

## Why

Unit tests for the scenario-by-container matrix, synthetic with no Docker. The matrix is the scenario/container coverage view, and its tests verify the mapping without Docker.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
