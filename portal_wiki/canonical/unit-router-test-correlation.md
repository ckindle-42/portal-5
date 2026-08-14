---
id: unit-router-test-correlation
kind: mixed
title: "Router correlation tests \u2014 trace-id stamping contract"
sources:
- type: code
  path: tests/unit/router/test_correlation.py
  commit: dfa74e2e
claims: []
confidence: high
tags:
- authored-v1
- tests
- router
created_at: 1785795519.573695
updated_at: 1785795519.573695
---

This test file pins the router's correlation-id logging contract: every
log record emitted while a correlation id is set carries that id, and records
outside any request get a dash. The three functions under test — generate,
set/get, and the log filter — are the plumbing that lets a request's logs be
traced end to end.

## Why

The `p5-` prefix and fixed id length are a contract the whole observability
path depends on: a log line's `correlation_id` is what ties a pipeline request
across the router, the backend call, and the response. The dash-when-unset
behaviour matters because a log filter that raises (or stamps nothing) when no
id is active would break logging for non-request contexts entirely — the
filter must always be total, and the dash is that totality. The 15-character
shape is pinned so a future id change that breaks downstream parsing fails
here rather than in production logs.

## Interfaces

`new_correlation_id` generates an id, `set_correlation_id`/`get_correlation_id`
manage the current thread's id, and `CorrelationIdLogFilter.filter` stamps
`record.correlation_id`. The tests cover the round-trip, the shape, and both
filter states (set and unset).
