---
id: unit-sec-tests-test_response_loop
kind: mixed
title: "Security tests \u2014 test_response_loop"
sources:
- type: code
  path: portal/modules/security/tests/test_response_loop.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.9863942
updated_at: 1785800599.9863942
---

Unit tests for the security module's test_response_loop surface.

## Why

Tests for the response loop and threat-driven intake: the covered gap produces a response. The response loop is what keeps the system current by construction, and the tests pin the growth.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
