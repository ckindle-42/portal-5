---
id: unit-router-metrics
kind: mixed
title: "Router metrics \u2014 single registry, import-once collectors"
sources:
- type: code
  path: portal/platform/inference/router/metrics.py
  commit: a234187e
last_generated_commit: a234187e
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
- router
created_at: 1785798081.9114408
updated_at: 1785798081.9114408
---

`metrics.py` owns the single Prometheus `CollectorRegistry` and every Portal
5 collector — request counts, token usage, response times, energy, tool
calls, and the rest. It is imported by the router facade, state, power,
tools, and routing, and must be import-once safe.

## Why

Every router module reports metrics, and if each declared its own collectors
there would be duplicate-registration crashes and divergent names. One module
owns the registry so every collector is declared exactly once; the
import-once property matters under multiple uvicorn workers because each
process imports the module once and re-importing must not re-register. The
metrics are the observability backbone the `get_metrics_summary` tool and the
fleet dashboard read.

## Interfaces

Exports `_REGISTRY` and the individual collectors (counters, gauges,
histograms) named for their signal: `_requests_total`, `_tokens_per_second`,
`_tool_calls_total`, the power gauges, and so on.

## Gotchas

`PROMETHEUS_MULTIPROC_DIR` must be set before this module imports
prometheus_client — that is why the entry point sets it in `__main__` before
the app imports.
