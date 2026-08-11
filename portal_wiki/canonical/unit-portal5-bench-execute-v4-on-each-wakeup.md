---
id: unit-portal5-bench-execute-v4-on-each-wakeup
kind: what
title: "PORTAL5_BENCH_EXECUTE_V4 \u2014 On each wakeup"
sources:
- type: code
  path: tests/benchmarks/bench/cli.py
- type: code
  path: tests/benchmarks/bench/runners.py
- type: code
  path: tests/benchmarks/bench/results_io.py
last_generated_commit: 00b76bf5cb990c51c6cc8b508fb561e921230262
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.702064
updated_at: 1784946220.702064
---

1. Is the process alive? (`ps`), how far along? (tail the log, count completed
   tests vs planned).
2. If progressing: reschedule ~20–30 min out.
3. If stalled (no new completed test in roughly two cooldown intervals):
   diagnose — a model that won't load, an OOM, a hung backend. Note it, and
   either narrow the next run with `--model` / `--workspace` / `--persona`
   filters, or halt with evidence.
4. If finished: proceed to results + dashboard.

## Why

The bench CLI has no `--skip-model` flag; instead it supports filter args
(`--model` substring, `--workspace`, `--persona`) and a `--retry-failed`
resume that reloads the last results file and skips already-completed entries
via `_result_already_done` in `tests/benchmarks/bench/results_io.py`. A wakeup
check therefore judges progress from the log and the dry-run plan, and reacts
by scoping the run or stopping with evidence rather than waiting blindly for a
run that will never finish.
