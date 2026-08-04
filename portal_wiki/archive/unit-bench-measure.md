---
id: unit-bench-measure
kind: mixed
title: "Bench measure \u2014 streaming TPS timing core"
sources:
- type: code
  path: tests/benchmarks/bench/measure.py
  commit: 4283b625
last_generated_commit: 4283b625
claims: []
confidence: high
tags:
- authored-v1
- tests
- bench
created_at: 1785798434.657781
updated_at: 1785798434.657781
---

`measure.py` is the core TPS measurement: the shared httpx client, pipeline
warmup, and the streaming bench loop. It is the timing heart of the package,
extracted from `bench_tps.py`.

## Why

The measurement loop is where TPS numbers come from, and its design
determines whether those numbers mean anything: it streams the response
(rather than waiting for the whole body), times the tokens as they arrive,
and uses the shared client so warmup and measurement share one connection
pool. The `close_bench_client()` teardown (new in the extraction) replaces
the global-client teardown that previously lived in `main` — because a client
that is never closed leaks a connection pool, and a benchmark that leaks
connections run after run eventually measures a broken pool.

## Interfaces

The shared client, the pipeline warmup, and the streaming `bench_tps` core
that runs a prompt and returns the TPS figure.

## Gotchas

Streaming measurement is the contract — a non-streaming timing would include
the full-body buffering latency and report a lower TPS than the fleet
actually serves.
