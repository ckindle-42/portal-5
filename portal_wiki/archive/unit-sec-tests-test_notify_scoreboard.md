---
id: unit-sec-tests-test_notify_scoreboard
kind: mixed
title: "Security tests \u2014 test_notify_scoreboard"
sources:
- type: code
  path: portal/modules/security/tests/test_notify_scoreboard.py
  commit: 862c7b11
last_generated_commit: 862c7b11
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800626.563235
updated_at: 1785800626.563235
---

Unit tests for the security module's test_notify_scoreboard surface.

## Why

The scoreboard's scoring semantics are what the alert-fatigue and notification gates assert, so they must be pinned. A scoreboard that scored a hunt as a notification when it was a false alarm would misrepresent the hunt's quality.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
