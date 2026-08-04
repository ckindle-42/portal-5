---
id: unit-sec-tests-test_sweep_parallel
kind: mixed
title: "Security tests \u2014 test_sweep_parallel"
sources:
- type: code
  path: portal/modules/security/tests/test_sweep_parallel.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800626.5632472
updated_at: 1785800626.5632472
---

Unit tests for the security module's test_sweep_parallel surface.

## Why

A parallel sweep that corrupted its results or broke iteration would produce wrong verdicts. The parallelisation tests verify that correctness holds and iteration mode behaves under parallelism.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
