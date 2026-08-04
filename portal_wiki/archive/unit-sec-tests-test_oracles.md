---
id: unit-sec-tests-test_oracles
kind: mixed
title: "Security tests \u2014 test_oracles"
sources:
- type: code
  path: portal/modules/security/tests/test_oracles.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800626.5632372
updated_at: 1785800626.5632372
---

Unit tests for the security module's test_oracles surface.

## Why

An oracle is the definition of scenario success, and its tests pin the verification logic. A named oracle that judged success inconsistently would make scenario scores incomparable across models and runs.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
