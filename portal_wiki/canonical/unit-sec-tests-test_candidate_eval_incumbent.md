---
id: unit-sec-tests-test_candidate_eval_incumbent
kind: mixed
title: "Security tests \u2014 test_candidate_eval_incumbent"
sources:
- type: code
  path: portal/modules/security/tests/test_candidate_eval_incumbent.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800626.56322
updated_at: 1785800626.56322
---

Unit tests for the security module's test_candidate_eval_incumbent surface.

## Why

A wrongly resolved incumbent would compare the candidate against the wrong baseline model, making the evaluation verdict meaningless. The incumbent-resolution fix is what makes candidate evaluation compare against the current model rather than in a vacuum, so the resolution is pinned.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
