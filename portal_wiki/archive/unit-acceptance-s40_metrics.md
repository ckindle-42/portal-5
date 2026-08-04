---
id: unit-acceptance-s40_metrics
kind: mixed
title: "S40 \u2014 Metrics"
sources:
- type: code
  path: tests/acceptance/s40_metrics.py
  commit: a88ad75b
last_generated_commit: a88ad75b
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799816.395905
updated_at: 1785799816.395905
---

This is the acceptance section s40_metrics. S40 — Metrics

## Why

It verifies the metrics endpoints report, so the telemetry the dashboards read is actually produced. A metrics path that returns nothing would make the fleet look unmeasured — the dashboards would show no data and no one would know the pipeline stopped reporting.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
