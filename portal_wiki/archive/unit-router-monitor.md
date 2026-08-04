---
id: unit-router-monitor
kind: mixed
title: "Router monitor \u2014 memory pressure valve + load sequencing"
sources:
- type: code
  path: portal/platform/inference/router/monitor.py
  commit: a234187e
last_generated_commit: a234187e
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
- router
created_at: 1785798087.896048
updated_at: 1785798087.896048
---

`monitor.py` is the memory and health monitor: it reads host memory, purges
or restarts Ollama when memory pressure threatens model residency, and
waits for the backend to drain or a model to load.

## Why

Apple Silicon unified memory means the models and the OS share one pool, and
a runaway process that exhausts RAM forces Ollama to evict resident models —
killing the "pinned models stay resident" property the whole multi-model
serving design depends on. The monitor is the pressure valve: `purge_memory`
frees what it can and `restart_ollama` is the last resort, both gated so they
fire only under genuine pressure, not on a transient spike. The wait-for
functions are the load-sequencing helpers that let a warmup or a swap know
when the backend is actually ready.

## Interfaces

`memory_pct`, `free_ram_gb`, `purge_memory`, `restart_ollama`,
`wait_for_drain`/`wait_for_drain_async`, and `wait_for_model_loaded`.

## Gotchas

`restart_ollama` is disruptive — every resident model has to reload — so it
must only be reached after purge has failed to relieve pressure, never as a
first response.
