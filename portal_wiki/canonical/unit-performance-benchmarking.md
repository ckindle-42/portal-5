---
id: unit-performance-benchmarking
kind: what
title: "PERFORMANCE \u2014 Benchmarking"
sources:
- type: code
  path: tests/benchmarks/bench_tps.py
- type: code
  path: tests/benchmarks/bench/cli.py
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.510845
updated_at: 1784946220.510845
---

TPS benchmarking is driven by `tests/benchmarks/bench_tps.py`, a shim that forwards to the `tests.benchmarks.bench` package. A typical pipeline invocation is:

```
python3 tests/benchmarks/bench_tps.py --mode pipeline --workspace auto --runs 3
```

`--mode` accepts `direct` (raw Ollama), `pipeline` (workspaces through the portal pipeline), `personas` (persona routing), or `all`. `--workspace` filters pipeline runs to an exact workspace id and `--runs` sets the per-model trial count. Results are written to a timestamped JSON under `tests/benchmarks/results/` (`RESULTS_DIR`), and the CLI prints a summary ranking runs by `avg_tps`.

Running the same model through `direct` and `pipeline` modes is the intended way to measure the portal layer's per-request overhead, because both modes use the same shared bench client and warmup path, so the delta isolates routing, auth, and proxy cost from inference.

## Why

A benchmark is only useful if its numbers are comparable across runs. The harness warms each model to a loaded state before timing, reuses one HTTP client so connection setup is not measured, and unloads or drains models between tests so one run cannot contaminate the next. The direct-versus-pipeline comparison exists specifically to keep the portal's routing overhead visible instead of burying it inside a single end-to-end number.
