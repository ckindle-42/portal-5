---
id: unit-sec-tests-test_capture_enrichment
kind: mixed
title: "Security tests \u2014 test_capture_enrichment"
sources:
- type: code
  path: portal/modules/security/tests/test_capture_enrichment.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986315
updated_at: 1785800599.986315
---

Unit tests for the security module's test_capture_enrichment surface.

## Why

Tests for the capture-quality gate that decides whether a saved capture is usable for a bench. A bench that used a low-quality capture would produce numbers that look real, so the gate is pinned.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
