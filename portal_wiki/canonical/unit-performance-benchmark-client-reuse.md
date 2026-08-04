---
id: unit-performance-benchmark-client-reuse
kind: what
title: "PERFORMANCE \u2014 Benchmark Client Reuse"
sources:
- type: code
  path: tests/benchmarks/bench/measure.py
- type: code
  path: tests/benchmarks/bench_tps.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.510535
updated_at: 1784946220.510535
---

The TPS benchmark reuses a single `httpx.Client` across all runs. `_get_bench_client()` in `tests/benchmarks/bench/measure.py` lazily creates a module-level `_bench_client` on first use and returns it for every subsequent `bench_tps()` call, with the pool configured as `httpx.Limits(max_keepalive_connections=10, max_connections=20)`.

`bench_tps.py` itself is now a thin entry-point shim that re-exports `bench_tps` from the `tests.benchmarks.bench` package, so the reuse lives in `measure.py` while the operator-facing command line is unchanged. The pipeline warmup step (`_warmup_pipeline_model`) deliberately opens a throwaway client because it runs before timing starts.

## Why

Reusing the client matters because the benchmark measures pipeline latency, and a fresh `httpx.Client` per run would fold TCP connect and TLS handshake cost into every measured request. Connection reuse keeps the measured number close to true inference throughput, so the comparison between direct and pipeline modes stays a comparison of the serving paths rather than of client setup overhead.
