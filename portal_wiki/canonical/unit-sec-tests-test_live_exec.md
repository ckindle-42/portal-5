---
id: unit-sec-tests-test_live_exec
kind: mixed
title: "Security tests \u2014 test_live_exec"
sources:
- type: code
  path: portal/modules/security/tests/test_live_exec.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800626.563231
updated_at: 1785800626.563231
---

Unit tests for the security module's test_live_exec surface.

## Why

The verified-without-evidence path is the failure this gate prevents: no path may emit verified without real evidence. The live-lab execution foundation tests guard that governing rule so a run cannot claim verification it did not earn.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
