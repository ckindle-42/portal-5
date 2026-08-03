---
id: unit-sec-tests-test_loop_notify
kind: mixed
title: "Security tests \u2014 test_loop_notify"
sources:
- type: code
  path: portal/modules/security/tests/test_loop_notify.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800626.5632331
updated_at: 1785800626.5632331
---

Unit tests for the security module's test_loop_notify surface.

## Why

The notification-to-resume-command wiring is what makes the loop operable from an alert. The loop notification and checkpoint/resume tests pin that an escalation carries the exact command an operator can run to resume.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
