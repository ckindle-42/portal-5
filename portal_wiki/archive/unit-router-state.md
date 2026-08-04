---
id: unit-router-state
kind: mixed
title: "Router state \u2014 metrics persistence + event recorders"
sources:
- type: code
  path: portal/platform/inference/router/state.py
  commit: a234187e
last_generated_commit: a234187e
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
- router
created_at: 1785798111.6230679
updated_at: 1785798111.6230679
---

`state.py` handles metrics-state persistence: it loads and saves the JSON
metrics snapshot, runs the periodic save loop, and records per-event
error/persona counters. It depends only on metrics and never imports
`router_pipe`.

## Why

The pipeline is stateless for conversation routing, but it does persist
operational metrics so the telemetry survives restarts. The state module owns
that persistence — the snapshot file, the save loop, and the counters that
feed it. The import discipline (metrics only) is what lets the telemetry
layer be reasoned about independently of the routing engine, and the
never-import-router_pipe rule keeps the circularity out.

## Interfaces

`_load_state`, `_save_state`, `_state_save_loop`, `_record_error`,
`_record_persona`, and the counters (`_request_count`, `_total_tps`, etc.)
that the state snapshot aggregates.

## Gotchas

The persisted state is telemetry, not conversation — the Rule 4 boundary
that keeps the pipeline stateless for routing is exactly what this module's
scope protects.
