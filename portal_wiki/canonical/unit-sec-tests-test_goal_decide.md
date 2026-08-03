---
id: unit-sec-tests-test_goal_decide
kind: mixed
title: "Security tests \u2014 test_goal_decide"
sources:
- type: code
  path: portal/modules/security/tests/test_goal_decide.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.9863412
updated_at: 1785800599.9863412
---

Unit tests for the security module's test_goal_decide surface.

## Why

Tests for goal-driven decide, hermetically with no model or lab. The decide logic must be correct without a model, so all decisions are verified in isolation.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
