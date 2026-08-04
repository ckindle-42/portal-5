---
id: unit-bench-runners
kind: mixed
title: "Bench runners \u2014 direct/pipeline/persona measurement paths"
sources:
- type: code
  path: tests/benchmarks/bench/runners.py
  commit: 4283b625
last_generated_commit: 4283b625
claims: []
confidence: high
tags:
- authored-v1
- tests
- bench
created_at: 1785798459.614971
updated_at: 1785798459.614971
---

`runners.py` is the bench runner surface: `bench_direct` measures models
directly against Ollama, `bench_pipeline` measures them through the pipeline
workspaces, and `bench_personas` measures persona-routed requests.

## Why

The three runners exist because "how fast is this model" has three valid
answers depending on the path: raw backend throughput (direct), the
production path the user actually hits (pipeline), and the persona-routed
path with its injection overhead (personas). A fleet decision needs all
three — a model that is fast raw but slow behind routing is a routing
problem, not a model problem, and only measuring through the pipeline shows
that. The runners were extracted with two dead conditionals collapsed, which
the module notes explicitly so a future reader knows the collapse was
deliberate.

## Interfaces

`bench_direct`, `bench_pipeline`, and `bench_personas` are the three
runners, each returning the result rows the CLI reports.

## Gotchas

The three runners measure different paths by design — comparing a direct
number to a pipeline number as if they were the same measurement is the
error this split exists to prevent.
