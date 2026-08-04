---
id: unit-sec-tests-test_prerun_readiness
kind: mixed
title: "Security tests \u2014 test_prerun_readiness"
sources:
- type: code
  path: portal/modules/security/tests/test_prerun_readiness.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986382
updated_at: 1785800599.986382
---

Unit tests for the security module's test_prerun_readiness surface.

## Why

Unit tests for pre-run readiness: the blue-scorable invariant and SPL coverage. A run that starts without the readiness invariants would produce results that cannot be scored.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
