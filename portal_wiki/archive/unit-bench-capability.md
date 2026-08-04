---
id: unit-bench-capability
kind: mixed
title: "Bench capability \u2014 execution-scored reasoning-aware probes"
sources:
- type: code
  path: tests/benchmarks/bench_capability.py
  commit: f09fdb85
last_generated_commit: f09fdb85
claims: []
confidence: high
tags:
- authored-v1
- tests
- bench
created_at: 1785798594.049841
updated_at: 1785798594.049841
---

`bench_capability.py` is the capability bench with reasoning-aware scoring:
it strips all leading reasoning (not just think tags), applies token budgets
per reasoning capability, runs multi-turn agentic loops with planted errors,
and scores by execution rather than keyword bingo, reporting format and
capability scores separately.

## Why

The capability bench exists because keyword-on-preamble scoring rewards a
model that *says* the right thing over one that *does* it. Scoring by
execution — does the model actually complete the task, and does it recover
from the planted error — is the difference between a capability claim and a
capability. The reasoning stripping and per-capability token budgets exist
because a model that spends its budget on reasoning never reaches the
capability, which a naive scorer would misread as a failure of the
capability itself. Held-out variants are the anti-overfit guard: >=3 prompts
per capability plus variants means a model that memorised a benchmark prompt
does not pass on that alone.

## Interfaces

The capability runners, the reasoning-aware token budgeting, the
format/capability score split, and the planted-error agentic loop.

## Gotchas

`capability_lib.py` shares this design — the score split and the execution
basis are the contract both files implement, and a change to one must match
the other.
