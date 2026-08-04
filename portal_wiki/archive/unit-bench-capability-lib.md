---
id: unit-bench-capability-lib
kind: mixed
title: "Bench capability lib \u2014 shared reasoning-aware scoring"
sources:
- type: code
  path: tests/benchmarks/capability_lib.py
  commit: f09fdb85
last_generated_commit: f09fdb85
claims: []
confidence: high
tags:
- authored-v1
- tests
- bench
created_at: 1785798623.4842172
updated_at: 1785798623.4842172
---

`capability_lib.py` is the shared helper library for the capability bench:
the final-answer extraction that strips all leading reasoning, the
reasoning-aware token budgets, and the execution-based capability scoring.

## Why

The capability scoring is a contract shared across the bench files, and the
library centralises it: `extract_final_answer` strips reasoning so the score
reflects the answer not the preamble, the token budgets account for
reasoning models' overhead, and the execute/validate scoring is the
capability judgment. Keeping it in a library (rather than duplicated in each
bench) means a scoring change applies everywhere it is used and cannot drift
between files.

## Interfaces

`extract_final_answer`, the token-budget helpers, and the capability
scoring functions.

## Gotchas

`bench_capability.py` implements the same design — a change to the scoring
basis in one must be mirrored in the other, which is why the library is the
better home for the shared pieces.
