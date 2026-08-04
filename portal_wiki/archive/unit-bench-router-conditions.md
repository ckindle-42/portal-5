---
id: unit-bench-router-conditions
kind: mixed
title: "Bench router conditions \u2014 VRAM-pressure router eviction"
sources:
- type: code
  path: tests/benchmarks/bench_router_conditions.py
  commit: f09fdb85
last_generated_commit: f09fdb85
claims: []
confidence: high
tags:
- authored-v1
- tests
- bench
created_at: 1785798607.901281
updated_at: 1785798607.901281
---

`bench_router_conditions.py` answers a specific operational question: does
VRAM pressure from inference models cause the LLM router to be evicted, and
how badly does that hurt routing quality and latency under real-world
conditions?

## Why

The router model and the inference models share Apple Silicon unified
memory, and a router that gets evicted whenever a big inference model loads
would silently add cold-start latency to every routed request and, worse,
risk routing degradation. The bench deliberately creates the pressure
condition (a big primary model and a standby model resident together) and
measures what happens to the router — because the failure mode only appears
under real load, and a bench that never applies pressure would certify a
router that collapses in production.

## Interfaces

The script sets up the candidate models, applies the memory pressure, and
measures router eviction, routing quality, and latency.

## Gotchas

This is a live-memory experiment — its numbers are specific to the device's
unified memory and must be re-measured on different hardware.
