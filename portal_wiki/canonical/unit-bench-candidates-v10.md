---
id: unit-bench-candidates-v10
kind: mixed
title: "Bench V10 candidates \u2014 claim-targeted capability probes"
sources:
- type: code
  path: tests/benchmarks/bench_candidates_v10.py
  commit: f09fdb85
claims: []
confidence: high
tags:
- authored-v1
- tests
- bench
created_at: 1785798590.572711
updated_at: 1785798590.572711
---

The V10 candidate bench runs targeted capability probes against the V10
candidate model set, going beyond what the generic TPS prompts measure:
multi-turn tool-call chains, language world-model env-state prediction,
long-context recall, and uncensored-versus-refusal behaviour — the specific
claims the V10 candidates make.

## Why

The generic bench_tps prompts measure throughput on generic categories, and
throughput does not answer whether a candidate actually delivers its claimed
capability. Each V10 candidate makes a distinctive claim (the tool-chain
model, the AgentWorld model, the long-context model, the uncensored model),
and a bench that does not probe that claim would certify a candidate on
irrelevant measures. The targeted probes exist so a V10 decision is made on
whether each model does what it promises, not on TPS alone.

## Interfaces

The script drives the candidate-specific probes and reports per-candidate
capability results against the claims.

## Gotchas

The probes are claim-specific by design — a candidate evaluated on a
different candidate's probe would show poorly for reasons unrelated to its
own value.
