---
id: unit-sec-tests-test_replay_captured_red_no_evidence
kind: mixed
title: "Security tests \u2014 test_replay_captured_red_no_evidence"
sources:
- type: code
  path: portal/modules/security/tests/test_replay_captured_red_no_evidence.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800626.5632389
updated_at: 1785800626.5632389
---

Unit tests for the security module's test_replay_captured_red_no_evidence surface.

## Why

The no-evidence case is the edge the regression covers: the replay path must not crash when no captured red evidence exists. A crash on the empty case would break a legitimate replay run, so the regression is pinned.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
