---
id: unit-sec-tests-test_ablation_attribution
kind: mixed
title: "Security tests \u2014 test_ablation_attribution"
sources:
- type: code
  path: portal/modules/security/tests/test_ablation_attribution.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986262
updated_at: 1785800599.986262
---

Unit tests for the security module's test_ablation_attribution surface.

## Why

Fixture coverage for the failure-attribution instrument's implementation behaviour. The module's own docstring is explicit that fixture coverage establishes behaviour only, not validity on live traces — so these tests pin the implementation without overclaiming.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
