---
id: unit-sec-tests-test_matrix
kind: mixed
title: "Security tests \u2014 test_matrix"
sources:
- type: code
  path: portal/modules/security/tests/test_matrix.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986368
updated_at: 1785800599.986368
---

Unit tests for the security module's test_matrix surface.

## Why

Unit tests for the scenario-by-container matrix, synthetic with no Docker. The matrix is the scenario/container coverage view, and its tests verify the mapping without Docker.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
