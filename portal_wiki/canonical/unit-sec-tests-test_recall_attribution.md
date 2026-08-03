---
id: unit-sec-tests-test_recall_attribution
kind: mixed
title: "Security tests \u2014 test_recall_attribution"
sources:
- type: code
  path: portal/modules/security/tests/test_recall_attribution.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800626.563238
updated_at: 1785800626.563238
---

Unit tests for the security module's test_recall_attribution surface.

## Why

The instrument separates retrieval failure from model failure, and its tests pin the discrimination. Without the attribution, a miss caused by absent telemetry would be blamed on the model, corrupting the eval's conclusions.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
