---
id: unit-sec-tests-test_ci_parity
kind: mixed
title: "Security tests \u2014 test_ci_parity"
sources:
- type: code
  path: portal/modules/security/tests/test_ci_parity.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.9863172
updated_at: 1785800599.9863172
---

Unit tests for the security module's test_ci_parity surface.

## Why

Unit tests for CI/local parity, guarding the gap that forced fix-churn after every push. The parity tests are what catch a suite that passes locally but fails in the clean CI environment.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
