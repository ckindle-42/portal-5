---
id: unit-sec-tests-test_rbp_episode_grounding
kind: mixed
title: "Security tests \u2014 test_rbp_episode_grounding"
sources:
- type: code
  path: portal/modules/security/tests/test_rbp_episode_grounding.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986384
updated_at: 1785800599.986384
---

Unit tests for the security module's test_rbp_episode_grounding surface.

## Why

Tests for the RBP evidence-episode grounding: an episode created per run with deterministic evidence. The per-run episode and its deterministic evidence are what make the run's record trustworthy.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
