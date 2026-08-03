---
id: unit-inference-main
kind: mixed
title: "Pipeline entry \u2014 uvicorn launcher with Prometheus setup"
sources:
- type: code
  path: portal/platform/inference/__main__.py
  commit: 5fbf51f8
last_generated_commit: 5fbf51f8
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
created_at: 1785797742.774378
updated_at: 1785797742.774378
---

The pipeline entry point is the uvicorn launcher for the router app. It
reads the port and worker count from the environment, sets up Prometheus
multiprocess mode, and serves `portal.platform.inference.router_pipe:app`.

## Why

The launcher encapsulates the operational decisions that must hold before the
app starts: workers default to CPU count capped at four (the pipeline is
I/O-bound proxying to Ollama, so a few workers help but memory bounds it),
and Prometheus multiprocess mode must be configured *before* the metrics
client is imported — with multiple workers each process needs a shared
metrics directory, and getting that wrong silently corrupts every metric.

## Interfaces

`main()` reads `PIPELINE_PORT` (default 9099), `PIPELINE_WORKERS`, and
`LOG_LEVEL`, creates the metrics temp dir if unset, and starts uvicorn on the
router app.

## Gotchas

The metrics temp dir is created with `mkdtemp` and never cleaned — deliberate
for a process that owns its lifetime, but a restart leaks a small directory
per run.
