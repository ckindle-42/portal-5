---
id: unit-bench-results-io
kind: mixed
title: "Bench results IO \u2014 crash-safe incremental persistence"
sources:
- type: code
  path: tests/benchmarks/bench/results_io.py
  commit: 4283b625
last_generated_commit: 4283b625
claims: []
confidence: high
tags:
- authored-v1
- tests
- bench
created_at: 1785798456.148909
updated_at: 1785798456.148909
---

`results_io.py` is the crash-safe incremental JSON persistence for bench
runs: it writes results incrementally so a run interrupted mid-way keeps the
results it already produced.

## Why

A TPS bench can run for hours, and a crash that loses everything is a
catastrophic waste — the checkpoint discipline the project enforces on
sweeps is the same principle encoded here. Incremental writes mean a crash
at minute 50 keeps the 50 minutes of results, and the JSON format keeps the
output portable for downstream analysis.

## Interfaces

The incremental writer and reader over the results directory.

## Gotchas

The incremental contract means the output file is appended to across the
run — a consumer reading it mid-run sees partial data, which is why the run
completion is marked explicitly in the output.
