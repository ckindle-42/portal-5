---
id: unit-sec-tests-test_bench_security_lab_gate
kind: mixed
title: "Security tests \u2014 test_bench_security_lab_gate"
sources:
- type: code
  path: portal/modules/security/tests/test_bench_security_lab_gate.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.98628
updated_at: 1785800599.98628
---

Unit tests for the security module's test_bench_security_lab_gate surface.

## Why

Unit tests for the lab reachability gate and the raw-output capture wrapper, pure logic with mocks. A bench that ran against an unreachable lab would produce garbage results, so the gate and the capture wrapper are pinned.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
