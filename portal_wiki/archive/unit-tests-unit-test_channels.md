---
id: unit-tests-unit-test_channels
kind: mixed
title: "Unit tests \u2014 test_channels"
sources:
- type: code
  path: tests/unit/test_channels.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892237
updated_at: 1785800468.892237
---

Unit tests for test_channels.

## Why

The channel adapters are the messenger front door, and their tests verify the routing and payload behaviour without a live messenger. A channel that sent the wrong workspace's response, or failed to thread a reply, would confuse every operator using it.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
