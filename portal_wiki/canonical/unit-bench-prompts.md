---
id: unit-bench-prompts
kind: mixed
title: "Bench prompts \u2014 category-targeted token-stable prompts"
sources:
- type: code
  path: tests/benchmarks/bench/prompts.py
  commit: 4283b625
last_generated_commit: 4283b625
claims: []
confidence: high
tags:
- authored-v1
- tests
- bench
created_at: 1785798444.1023612
updated_at: 1785798444.1023612
---

`prompts.py` is the bench's prompt library and category map: category-mapped
prompts designed to produce roughly 150-250 tokens of structured output, so
TPS comparisons are apples-to-apples within a category. The general prompt is
the fallback.

## Why

TPS measured on one-token answers and TPS measured on a 300-token structured
response are different numbers, and mixing them corrupts the comparison. The
prompt library exists so every measurement in a category exercises the same
kind of generation, and the token target (~150-250) is chosen because it is
the realistic workload of the fleet — short enough to be fast, long enough
to be a real generation. Category mapping is what lets an operator compare
the coding models fairly against each other without a general-prompt model
skewing the comparison.

## Interfaces

`PROMPTS` maps category names to prompt strings; the category maps and the
fallback are the surface the measurement and CLI consume.

## Gotchas

The token target is the contract — a prompt that produces 20 tokens or 2000
would not be measuring the same thing as its category siblings.
