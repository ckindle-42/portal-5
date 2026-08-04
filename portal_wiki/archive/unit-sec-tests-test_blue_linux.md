---
id: unit-sec-tests-test_blue_linux
kind: mixed
title: "Security tests \u2014 test_blue_linux"
sources:
- type: code
  path: portal/modules/security/tests/test_blue_linux.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986285
updated_at: 1785800599.986285
---

Unit tests for the security module's test_blue_linux surface.

## Why

Unit tests for the Linux and web blue telemetry plus purple convergence, synthetic or dry-run. The Linux telemetry path is exercised hermetically so the blue loop's Linux handling is verified without a live lab.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
