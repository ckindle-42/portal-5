---
id: unit-sec-tests-test_sweep_confidence
kind: mixed
title: "Security tests \u2014 test_sweep_confidence"
sources:
- type: code
  path: portal/modules/security/tests/test_sweep_confidence.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800626.563245
updated_at: 1785800626.563245
---

Unit tests for the security module's test_sweep_confidence surface.

## Why

The bootstrap confidence interval is what makes a sweep verdict statistically honest. A verdict without a confidence bound is a guess, so the tests pin the bootstrap computation and the verdict logic.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
