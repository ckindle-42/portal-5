---
id: unit-bench-router
kind: mixed
title: "Bench router \u2014 router-candidate classification accuracy"
sources:
- type: code
  path: tests/benchmarks/bench_router.py
  commit: f09fdb85
last_generated_commit: f09fdb85
claims: []
confidence: high
tags:
- authored-v1
- tests
- bench
created_at: 1785798604.420969
updated_at: 1785798604.420969
---

`bench_router.py` benchmarks the LLM router candidate models directly,
comparing how the router candidates classify routing examples against the
expected workspace.

## Why

The router's accuracy is the Layer-1 routing quality, and a router candidate
that misclassifies too often silently misroutes user requests. The bench
measures each router candidate against the routing examples so a router
model change is justified by data — the candidate must not regress the
classification accuracy that the routing layer depends on. It is the
measurement that keeps the router's 82% accuracy claim honest.

## Interfaces

The script drives each router candidate over the routing corpus and reports
classification accuracy per candidate.

## Gotchas

The bench measures classification, not latency — a router that is accurate
but slow has a separate cost profile, measured elsewhere.
