---
id: unit-sec-tests-test_continuous_eval
kind: mixed
title: "Security tests \u2014 test_continuous_eval"
sources:
- type: code
  path: portal/modules/security/tests/test_continuous_eval.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986325
updated_at: 1785800599.986325
---

Unit tests for the security module's test_continuous_eval surface.

## Why

Tests for continuous evaluation and content growth: corpus growth from closed gaps. The continuous loop's growth is what keeps coverage current, and the tests pin the growth mechanics.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
