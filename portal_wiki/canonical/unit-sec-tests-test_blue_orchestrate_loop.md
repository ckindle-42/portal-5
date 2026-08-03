---
id: unit-sec-tests-test_blue_orchestrate_loop
kind: mixed
title: "Security tests \u2014 test_blue_orchestrate_loop"
sources:
- type: code
  path: portal/modules/security/tests/test_blue_orchestrate_loop.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800626.563212
updated_at: 1785800626.563212
---

Unit tests for the security module's test_blue_orchestrate_loop surface.

## Why

The orchestration order is the contract of the blue loop, and the tests pin the deterministic sequencing of the section pipeline. A loop that reordered its sections would feed the wrong material to each stage, so the exact order is what these tests lock down.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
