---
id: unit-sec-tests-test_emergent_gaps
kind: mixed
title: "Security tests \u2014 test_emergent_gaps"
sources:
- type: code
  path: portal/modules/security/tests/test_emergent_gaps.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986332
updated_at: 1785800599.986332
---

Unit tests for the security module's test_emergent_gaps surface.

## Why

Tests that an emergent miss becomes a red-only gap and synthetic misses are excluded. The exclusion of synthetic misses is what keeps the gap engine from crying wolf on test data.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
