---
id: unit-sec-tests-test_analyst_verdict
kind: mixed
title: "Security tests \u2014 test_analyst_verdict"
sources:
- type: code
  path: portal/modules/security/tests/test_analyst_verdict.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986271
updated_at: 1785800599.986271
---

Unit tests for the security module's test_analyst_verdict surface.

## Why

Tests for the analyst-verdict taxonomy extended with the similar/variant/novel axis. The emerging-threat case must be representable, and these tests pin the extended verdict shape.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
