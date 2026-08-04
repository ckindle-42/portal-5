---
id: unit-sec-tests-test_sweep_checkpoint_safety
kind: mixed
title: "Security tests \u2014 test_sweep_checkpoint_safety"
sources:
- type: code
  path: portal/modules/security/tests/test_sweep_checkpoint_safety.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800626.563244
updated_at: 1785800626.563244
---

Unit tests for the security module's test_sweep_checkpoint_safety surface.

## Why

The original devstral raw-versus-harness incident was a checkpoint loss, and these tests pin the prevention. A sweep that lost its checkpoint on interruption would discard hours of completed work, so the safety is verified.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
