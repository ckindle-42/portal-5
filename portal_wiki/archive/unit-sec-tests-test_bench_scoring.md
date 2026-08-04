---
id: unit-sec-tests-test_bench_scoring
kind: mixed
title: "Security tests \u2014 test_bench_scoring"
sources:
- type: code
  path: portal/modules/security/tests/test_bench_scoring.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.9862778
updated_at: 1785800599.9862778
---

Unit tests for the security module's test_bench_scoring surface.

## Why

Unit tests for the bench scoring pure functions, all in-memory. The scoring functions are the verdict logic of every bench, and their tests pin the pure computation without a backend.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
