---
id: unit-surface-benchmarks
kind: mixed
title: "Bench harnesses \u2014 TPS, capability, security, and router measurement"
sources:
- type: code
  path: tests/benchmarks/*.py
- type: code
  path: tests/benchmarks/bench/*.py
last_generated_commit: 778def71961fd1bb2f1088be9754388706facf7a
claims: []
confidence: high
tags:
- authored-v1
- tests
- benchmarks
created_at: 1785883200.0
updated_at: 1785883200.0
---

Under `tests/benchmarks/`, the bench harnesses measure the fleet along four axes: raw TPS, capability execution, security-phase latency, and router classification. The TPS harness is the `bench/` package, decomposed from the former monolithic `bench_tps.py`: a freshness-checked CLI orchestrates a config-driven fleet plan through lifecycle warmup, streaming measurement, tiered reporting, and incremental persistence, with an adhoc probe for unregistered candidates. The capability, security, and router scripts sit beside it.

## Why

Every fleet decision claims to be justified by numbers, and a figure that does not survive scrutiny is worse than none, so each harness encodes the conditions under which its number is honest: TPS only when the model is resident and warm, capability only when scored by execution, attack latency only measured phase by phase against a live lab, and router accuracy only under VRAM pressure. The disciplines that stop a misleading result from being reported as a real one — empty retries once, timeouts never, pings fire-and-forget, matrices without verdicts — are part of the same contract.

## Interfaces

The `bench/` package exposes `bench_direct`, `bench_pipeline`, and `bench_personas` as the measurement paths, `probe_models` for unregistered candidates, and `close_bench_client` for teardown, all re-exported through `bench_tps.py`. `capability_lib.py` holds the shared `extract_final_answer` scoring; `bench_security.py` re-exports the security-core implementation.

## Gotchas

A scoring change in the capability bench must be mirrored in its shared library; an empty generation is retried once but a timeout is never; direct and pipeline figures are not comparable, and the adhoc probe measures the raw model rather than routing.
