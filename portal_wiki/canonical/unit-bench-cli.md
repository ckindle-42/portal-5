---
id: unit-bench-cli
kind: mixed
title: "Bench CLI \u2014 freshness-checked TPS run orchestration"
sources:
- type: code
  path: tests/benchmarks/bench/cli.py
  commit: 4283b625
last_generated_commit: 4283b625
claims: []
confidence: high
tags:
- authored-v1
- tests
- bench
created_at: 1785798419.12552
updated_at: 1785798419.12552
---

`cli.py` is the bench CLI entry point: argument parsing, the image-freshness
check, and run orchestration. It was extracted from `bench_tps.py` with the
shared client teardown routed through `measure.close_bench_client()`.

## Why

The CLI is the operator surface for a TPS run — model filters, prompt
categories, run counts, output paths — and the image-freshness check it runs
before starting is the guard against the stalest failure mode in this
project: benchmarking against a stale Docker image and reporting numbers for
code that is not running. Extracting the CLI from the measurement core keeps
argument handling separate from the timing logic so a CLI change never
touches the measurement.

## Interfaces

Argument parsing, the freshness check, and the orchestration that wires the
runners to the output. `main` is the entry.

## Gotchas

The freshness check matters: a bench run against a stale pipeline image
produces numbers for the wrong code, and the CLI is where that is caught
before hours of measurement.
