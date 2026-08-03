---
id: unit-sec-tests-test_perception_scope
kind: mixed
title: "Security tests \u2014 test_perception_scope"
sources:
- type: code
  path: portal/modules/security/tests/test_perception_scope.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986377
updated_at: 1785800599.986377
---

Unit tests for the security module's test_perception_scope surface.

## Why

Tests for the lab-scope guard invariant, testable without the lab up. The scope guard must be verifiable before the lab exists, which is why it is tested in isolation.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
