---
id: unit-sec-tests-test_web_exec_coverage
kind: mixed
title: "Security tests \u2014 test_web_exec_coverage"
sources:
- type: code
  path: portal/modules/security/tests/test_web_exec_coverage.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986444
updated_at: 1785800599.986444
---

Unit tests for the security module's test_web_exec_coverage surface.

## Why

Unit tests for web-exploit scenario coverage: new scenarios have valid structure. A malformed web scenario would fail for the wrong reason, so the structure is validated.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
