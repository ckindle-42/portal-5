---
id: unit-tool-preselect-test-state
kind: mixed
title: "Preselector state tests \u2014 auto-disable machine"
sources:
- type: code
  path: portal/platform/inference/tool_preselect/tests/test_state.py
  commit: 50d41b55
last_generated_commit: 50d41b55
claims: []
confidence: high
tags:
- authored-v1
- platform
- tool-preselect
- tests
created_at: 1785796866.2845812
updated_at: 1785796866.2845812
---

This test file pins the preselector's auto-disable state machine: recording
outcomes, accumulating misses, and flipping a workspace to auto-disabled.

## Why

Auto-disable is the feedback loop that makes the feature safe, and its
threshold is the one behaviour an operator might reasonably tune — so the
test that pins "enough consecutive misses disables the workspace" is what
stops a threshold change from silently enabling preselection for a workspace
the ranker cannot serve. The per-workspace isolation is equally worth
pinning: one bad workspace must not disable another.

## Interfaces

The suite drives `record_outcome`, `is_auto_disabled`, and `reset`,
asserting the miss accumulation, the disable flip, and the reset clearing
state for one workspace or all.

## Gotchas

Because the state is module-global, the tests must reset it between cases
(and the suite's reset coverage is itself part of the contract — a state
layer that cannot be reset is a state layer that leaks across tests and,
worse, across real runs).
