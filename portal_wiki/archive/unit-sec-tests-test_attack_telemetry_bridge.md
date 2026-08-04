---
id: unit-sec-tests-test_attack_telemetry_bridge
kind: mixed
title: "Security tests \u2014 test_attack_telemetry_bridge"
sources:
- type: code
  path: portal/modules/security/tests/test_attack_telemetry_bridge.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986273
updated_at: 1785800599.986273
---

Unit tests for the security module's test_attack_telemetry_bridge surface.

## Why

Tests the principle that the red transcript is an audit and counterfactual plane, never sensor evidence. A transcript treated as sensor evidence would let the attacker's own report count as telemetry, so the boundary is asserted.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
