---
id: unit-bench-mbptl
kind: mixed
title: "Bench MBPTL \u2014 per-phase lab attack latency"
sources:
- type: code
  path: tests/benchmarks/bench_mbptl.py
  commit: f09fdb85
last_generated_commit: f09fdb85
claims: []
confidence: high
tags:
- authored-v1
- tests
- bench
created_at: 1785798597.483368
updated_at: 1785798597.483368
---

`bench_mbptl.py` times each attack phase of the Most Basic Penetration
Testing Lab (a 17-flag CTF) through the sandbox MCP, measuring real-world
attack latency end to end: web exploitation, SQL injection,
post-exploitation, pivoting, and binary exploitation.

## Why

The security bench's TPS numbers measure generation speed, but the question
the operator actually asks is "how fast can an agent work the lab?" —
generation speed is not attack latency. Measuring each phase through the
sandbox end to end is what produces the real-world number: how long does the
whole exploitation path take, not how fast a token flows. The per-phase
breakdown is what makes the result actionable — if SQLi is slow, the
operator sees it is SQLi, not "the agent is slow".

## Interfaces

The script drives each attack phase through the sandbox MCP and reports
per-phase latency.

## Gotchas

The bench requires the lab and the sandbox to be reachable — it is a live
measurement against real targets, not a unit test, and its numbers are
environment-specific.
