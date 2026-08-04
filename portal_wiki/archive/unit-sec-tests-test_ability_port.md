---
id: unit-sec-tests-test_ability_port
kind: mixed
title: "Security tests \u2014 test_ability_port"
sources:
- type: code
  path: portal/modules/security/tests/test_ability_port.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986258
updated_at: 1785800599.986258
---

Unit tests for the security module's test_ability_port surface.

## Why

Fidelity tests for the ported ptai probes, asserting the real detect functions rather than stubs. A probe tested against a stub would certify the wrapper while the real detection diverged, so the tests pin the actual ported behaviour.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
