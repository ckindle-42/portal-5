---
id: unit-sec-tests-test_growth_loop_blue_draft
kind: mixed
title: "Security tests \u2014 test_growth_loop_blue_draft"
sources:
- type: code
  path: portal/modules/security/tests/test_growth_loop_blue_draft.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800626.563228
updated_at: 1785800626.563228
---

Unit tests for the security module's test_growth_loop_blue_draft surface.

## Why

The gap-to-draft conversion is the growth loop's first step, and the tests pin that a red-only gap produces a draft detection. If the loop failed to draft from a gap, the whole self-improving mechanism would stall at the first step.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
