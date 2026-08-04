---
id: unit-bench-lifecycle
kind: mixed
title: "Bench lifecycle \u2014 warmup/unload/drain memory discipline"
sources:
- type: code
  path: tests/benchmarks/bench/lifecycle.py
  commit: 4283b625
last_generated_commit: 4283b625
claims: []
confidence: high
tags:
- authored-v1
- tests
- bench
created_at: 1785798431.1808069
updated_at: 1785798431.1808069
---

`lifecycle.py` is the backend health, warmup, unload, and Metal memory
lifecycle for the bench: it checks backend availability, warms up models,
unloads them between tiers, and drains pending work, delegating the drain
logic to `tests.memory_guard`.

## Why

TPS measurement is only valid when the model being measured is actually
resident and warm — a cold load inflates the first run's time and corrupts
the number. The lifecycle module owns that pre-condition: warmup isolates the
load penalty, unload frees memory between tiers so a bench does not evict its
own next subject, and the health checks are what let the bench report "Ollama
is down" instead of measuring nothing and presenting it as a result. The
drain delegation keeps the memory-discipline logic in one place rather than
duplicating it.

## Interfaces

The health checks, warmup, unload, idle, and drain functions, plus the
hardware-info helper that reports the device being measured.

## Gotchas

The warmup call is isolated from measurement — a bench that times the warmup
call would report a cold-load number as if it were steady-state TPS.
