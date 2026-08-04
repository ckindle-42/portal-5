---
id: unit-sec-tests-test_blue_grounding
kind: mixed
title: "Security tests \u2014 test_blue_grounding"
sources:
- type: code
  path: portal/modules/security/tests/test_blue_grounding.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986283
updated_at: 1785800599.986283
---

Unit tests for the security module's test_blue_grounding surface.

## Why

Tests for the cite-or-drop false-positive control: a reported technique with no telemetry evidence must be dropped. The grounding control is what stops the blue loop from citing techniques nothing in the telemetry supports.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
