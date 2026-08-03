---
id: unit-bench-empty-retry
kind: mixed
title: "Bench empty-retry test \u2014 empty-only retry guard"
sources:
- type: code
  path: tests/benchmarks/test_empty_retry.py
  commit: f09fdb85
last_generated_commit: f09fdb85
claims: []
confidence: high
tags:
- authored-v1
- tests
- bench
created_at: 1785798633.026751
updated_at: 1785798633.026751
---

`test_empty_retry.py` tests the bench's empty-output retry logic: an
empty-generation run is retried once and a successful retry promotes the
cell to `runs_success`, while timeouts and HTTP errors are never retried.

## Why

An empty generation is a specific, recoverable failure (the model produced
nothing — often a transient load artifact) worth one retry, whereas a timeout
or HTTP error is a real condition that a retry would merely mask. The test
pins the guard expression exactly: it replicates the `_run_with_empty_retry`
logic inline (because `_stream_one_run` is a closure inside `bench_tps`, not
a module attribute) so a change to the retry guard is caught by the test
rather than silently changing which failures get retried.

## Interfaces

The test exercises the exact guard expression from the bench runner with
synthetic outcomes.

## Gotchas

The inline-replication approach is deliberate and documented — the closure
shape means monkeypatching the internal is not possible, so the test
re-implements the guard to pin it.
