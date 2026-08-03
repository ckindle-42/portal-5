---
id: unit-sec-tests-test_loop
kind: mixed
title: "Security tests \u2014 test_loop"
sources:
- type: code
  path: portal/modules/security/tests/test_loop.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800626.563232
updated_at: 1785800626.563232
---

Unit tests for the security module's test_loop surface.

## Why

The loop's iteration and escalation semantics are pinned without a live engagement. An autonomous loop that iterated wrong or escalated prematurely would either stall or burn budget, so the synthetic tests verify the loop logic.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
