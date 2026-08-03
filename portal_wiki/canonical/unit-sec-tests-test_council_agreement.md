---
id: unit-sec-tests-test_council_agreement
kind: mixed
title: "Security tests \u2014 test_council_agreement"
sources:
- type: code
  path: portal/modules/security/tests/test_council_agreement.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986327
updated_at: 1785800599.986327
---

Unit tests for the security module's test_council_agreement surface.

## Why

Tests for the council-of-agreement mechanism, the multi-interpreter vote over shared evidence. The quorum and seat-isolation semantics are the anti-groupthink design, and the tests pin them.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
