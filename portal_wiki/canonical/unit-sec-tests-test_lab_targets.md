---
id: unit-sec-tests-test_lab_targets
kind: mixed
title: "Security tests \u2014 test_lab_targets"
sources:
- type: code
  path: portal/modules/security/tests/test_lab_targets.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800626.5632288
updated_at: 1785800626.5632288
---

Unit tests for the security module's test_lab_targets surface.

## Why

A target catalog that named a nonexistent target would make every lab phase fail on a fiction. The lab targets catalog is the ground truth every later lab phase builds on, so its tests verify the catalog contents and shape.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
