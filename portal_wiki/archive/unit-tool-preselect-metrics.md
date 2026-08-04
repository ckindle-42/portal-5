---
id: unit-tool-preselect-metrics
kind: mixed
title: "Tool preselector metrics \u2014 outcome-label counters"
sources:
- type: code
  path: portal/platform/inference/tool_preselect/metrics.py
  commit: 50d41b55
last_generated_commit: 50d41b55
claims: []
confidence: high
tags:
- authored-v1
- platform
- tool-preselect
created_at: 1785796797.524894
updated_at: 1785796797.524894
---

`metrics.py` records the preselector's operational outcome labels to
Prometheus: each call, each miss, and each auto-disable, keyed by workspace.
The outcome labels (ok, fallback_timeout, fallback_lowconf, bypass_disabled,
etc.) are the observability vocabulary the preselector's health is judged by.

## Why

A feature that silently changes the request path needs to be observable, and
the outcome labels are the instrument: they distinguish a successful
narrowing from every fallback path, so an operator can see at a glance
whether preselection is narrowing tools or quietly doing nothing. The
metrics are how the "is it working?" question is answered with data instead
of guesswork, and the per-workspace keying is what lets a specific workspace
be investigated when its behaviour looks off.

## Interfaces

`record_preselect_call(workspace_id, ...)` increments the call counter with
its outcome label; `record_miss` marks a preselect miss; `record_auto_disabled`
marks a workspace auto-disabling. The counters follow the Prometheus naming
the fleet dashboard consumes.

## Gotchas

The metrics are counts, not the tuning signal — the auto-disable state in
`state.py` is what actually changes behaviour, so the two must be read
together (counts show the pattern, state shows the consequence).
