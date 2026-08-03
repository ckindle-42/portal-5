---
id: unit-sec-tests-test_bench_investigation
kind: mixed
title: "Security tests \u2014 test_bench_investigation"
sources:
- type: code
  path: portal/modules/security/tests/test_bench_investigation.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986275
updated_at: 1785800599.986275
---

Unit tests for the security module's test_bench_investigation surface.

## Why

Tests for the investigation benchmark: the single-agent baseline runs across all scenarios and the metrics compute. The baseline is the honesty ruler the multi-agent stack must beat, so its tests pin the baseline and the metric computation.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
