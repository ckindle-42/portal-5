---
id: unit-sec-tests-test_sandbox_output_cap
kind: mixed
title: "Security tests \u2014 test_sandbox_output_cap"
sources:
- type: code
  path: portal/modules/security/tests/test_sandbox_output_cap.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986397
updated_at: 1785800599.986397
---

Unit tests for the security module's test_sandbox_output_cap surface.

## Why

Regression guard for the red-tool-output truncation cap, found live. The cap prevents a tool's huge output from flooding the context, and the guard pins the truncation.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
