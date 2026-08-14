---
id: unit-portal5-bench-execute-v4-autonomous-monitoring-loop-required-default
kind: what
title: "PORTAL5_BENCH_EXECUTE_V4 \u2014 Autonomous Monitoring Loop \u2014 required\
  \ default"
sources:
- type: code
  path: tests/benchmarks/bench/cli.py
- type: code
  path: tests/benchmarks/bench/runners.py
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.7012339
updated_at: 1784946220.7012339
---

Full bench runs take hours: the default `--runs 5` multiplies every direct
model, pipeline workspace, and persona test, and each model swap is gated by a
cooldown and Metal-drain wait. Immediately after launching, establish a
periodic wakeup loop and keep it until the run finishes. Not optional —
long-running runs stall on OOM, hung backends, or a model that refuses to
load, and nobody notices until the wakeup checks.

## Why

The bench is deliberately slow: it unloads each Ollama model and waits for
Metal to drain before loading the next (`_wait_metal_drain` in
`tests/benchmarks/bench/lifecycle.py`) so TPS numbers are not skewed by
resident-model reuse. A multi-hour unattended run therefore cannot self-heal;
a wakeup loop is what turns a stalled overnight run into a diagnosed, resumed
one. This is why the V4 prompt made the loop a required default rather than a
suggestion.
