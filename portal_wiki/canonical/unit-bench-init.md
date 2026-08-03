---
id: unit-bench-init
kind: mixed
title: "Bench package \u2014 decomposed TPS measurement suite"
sources:
- type: code
  path: tests/benchmarks/bench/__init__.py
  commit: 4283b625
last_generated_commit: 4283b625
claims: []
confidence: high
tags:
- authored-v1
- tests
- bench
created_at: 1785798407.122365
updated_at: 1785798407.122365
---

The bench package is the TPS benchmark suite, decomposed from the former
monolithic `tests/benchmarks/bench_tps.py` into focused modules: config,
prompts, discovery, lifecycle, results IO, measure, and runners. It is the
performance-measurement surface the fleet's TPS numbers come from.

## Why

The monolith had grown past maintainability, and the decomposition exists so
each concern — prompt library, model discovery, warmup lifecycle, streaming
measurement, result persistence — is a module with one job. The module map
in the docstring is the contract for where a new bench feature belongs:
add a prompt to `prompts`, a discovery rule to `discovery`, a runner to
`runners`. Keeping the pieces separate is what lets the TPS measurement stay
stable while the fleet grows.

## Interfaces

The package exposes the runner entry points (`bench_direct`,
`bench_pipeline`, `bench_personas`) and the shared measurement core, with the
supporting modules behind them.

## Gotchas

Most modules note they were extracted byte-for-byte from `bench_tps.py` — a
new feature should go in the right module, not back into a hypothetical
monolith.
