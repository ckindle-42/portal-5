---
id: unit-tool-preselect-test-metrics
kind: mixed
title: "Preselector metrics tests \u2014 outcome counter contract"
sources:
- type: code
  path: portal/platform/inference/tool_preselect/tests/test_metrics.py
  commit: 50d41b55
last_generated_commit: 50d41b55
claims: []
confidence: high
tags:
- authored-v1
- platform
- tool-preselect
- tests
created_at: 1785796848.9780679
updated_at: 1785796848.9780679
---

This test file pins the preselector's Prometheus metrics: the call, miss, and
auto-disable counters and their outcome labels.

## Why

The outcome-label vocabulary is what an operator uses to judge whether the
preselector is working, and a metrics rename that every dashboard depends on
is a silent break if nothing asserts the current names. These tests hold the
counter contract stable so a refactor cannot relabel the outcomes without
this suite objecting.

## Interfaces

The suite drives `record_preselect_call`, `record_miss`, and
`record_auto_disabled`, asserting the counters increment with the expected
labels and per-workspace keying.

## Gotchas

Because the metrics are Prometheus counters, the tests must reset or isolate
the counter state between cases so an earlier test's increments do not leak
into the next assertion.
