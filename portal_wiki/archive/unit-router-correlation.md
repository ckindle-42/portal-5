---
id: unit-router-correlation
kind: mixed
title: "Router correlation \u2014 per-request trace-id stamping"
sources:
- type: code
  path: portal/platform/inference/router/correlation.py
  commit: a234187e
last_generated_commit: a234187e
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
- router
created_at: 1785798070.092612
updated_at: 1785798070.092612
---

`correlation.py` is the correlation-id plumbing: it generates, sets, and
reads a per-request id and stamps every log record with it via a middleware
and a logging filter.

## Why

A multi-hop request (pipeline → tool server → Ollama) generates logs across
processes, and without a correlation id there is no way to reassemble the
request's trail. The middleware assigns an id per request and the log filter
stamps each record, so grepping a correlation id reproduces the whole path.
The dash-when-unset behaviour keeps logging total — a record outside any
request gets a dash rather than crashing the filter.

## Interfaces

`new_correlation_id`, `set_correlation_id`, `get_correlation_id`,
`CorrelationIdMiddleware`, and `CorrelationIdLogFilter` are the surface;
`install_log_filter` attaches the filter.

## Gotchas

The id shape (`p5-` plus twelve chars) is a contract — the drift tests pin
both the shape and the dash fallback so downstream parsing cannot silently
break.
