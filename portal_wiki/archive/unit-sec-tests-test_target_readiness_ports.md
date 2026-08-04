---
id: unit-sec-tests-test_target_readiness_ports
kind: mixed
title: "Security tests \u2014 test_target_readiness_ports"
sources:
- type: code
  path: portal/modules/security/tests/test_target_readiness_ports.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800626.5632489
updated_at: 1785800626.5632489
---

Unit tests for the security module's test_target_readiness_ports surface.

## Why

A readiness gate that checked the wrong port would report a target ready when it is not. The target readiness gate and the port single-source-of-truth are what make readiness mean something, and the tests pin both.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
