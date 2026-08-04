---
id: unit-router-power
kind: mixed
title: "Router power \u2014 energy accounting from powermetrics"
sources:
- type: code
  path: portal/platform/inference/router/power.py
  commit: a234187e
last_generated_commit: a234187e
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
- router
created_at: 1785798093.8313239
updated_at: 1785798093.8313239
---

`power.py` reads the host powermetrics socket, converts watt-seconds to
USD, and records per-request energy and token usage into the metrics
collectors.

## Why

Energy accounting is a Portal 5-specific capability: each request's energy
cost is estimated from the host's power draw and charged to the workspace
that served it, so an operator can see which workloads cost real money to
run on the hardware. The watt-to-USD conversion (`ELECTRICITY_RATE_USD_PER_KWH`)
is what turns a hardware reading into an operating cost, and the per-workspace
energy gauges are what make the cost attributable. The module's import
discipline (it depends on metrics and state but never on `router_pipe`) keeps
it testable in isolation.

## Interfaces

`_power_polling_loop` samples the socket, `_record_usage` attributes energy
and tokens to a workspace, and the gauges in `metrics` carry the readings.

## Gotchas

The energy figures are estimates from the power socket, not metered billing —
accurate enough for relative cost comparison, not for an invoice.
