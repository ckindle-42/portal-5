---
id: unit-sec-tests-test_red_only_network_capture_wiring
kind: mixed
title: "Security tests \u2014 test_red_only_network_capture_wiring"
sources:
- type: code
  path: portal/modules/security/tests/test_red_only_network_capture_wiring.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986389
updated_at: 1785800599.986389
---

Unit tests for the security module's test_red_only_network_capture_wiring surface.

## Why

Regression guard that the red-only all-scenarios CLI loop actually starts and stops episode-scoped packet capture. A loop that never started the capture would produce captures that miss the episode.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
