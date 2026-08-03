---
id: unit-sec-tests-test_telemetry_contracts
kind: mixed
title: "Security tests \u2014 test_telemetry_contracts"
sources:
- type: code
  path: portal/modules/security/tests/test_telemetry_contracts.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986432
updated_at: 1785800599.986432
---

Unit tests for the security module's test_telemetry_contracts surface.

## Why

Tests for the canonical telemetry contracts: a single contract per source. Two contracts for one source is the dual-backend drift the canonicalisation removed, and the tests prevent its return.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
