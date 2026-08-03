---
id: unit-sec-tests-test_stage2_propose
kind: mixed
title: "Security tests \u2014 test_stage2_propose"
sources:
- type: code
  path: portal/modules/security/tests/test_stage2_propose.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986413
updated_at: 1785800599.986413
---

Unit tests for the security module's test_stage2_propose surface.

## Why

Unit tests for stage-2 propose, prove, and gate for oracle-tier promotions, synthetic. The propose/prove/gate pipeline is what promotes a technique to the oracle tier, and the tests pin the gate.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
