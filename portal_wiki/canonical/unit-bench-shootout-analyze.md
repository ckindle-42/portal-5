---
id: unit-bench-shootout-analyze
kind: mixed
title: "Bench shootout analyze \u2014 per-shape coding matrix"
sources:
- type: code
  path: tests/benchmarks/coding_shootout_analyze.py
  commit: f09fdb85
last_generated_commit: f09fdb85
claims: []
confidence: high
tags:
- authored-v1
- tests
- bench
created_at: 1785798629.4913752
updated_at: 1785798629.4913752
---

`coding_shootout_analyze.py` reads the persona-matrix output JSON for the
auto-coding-bench workspace and emits a per-shape-by-per-model capability
matrix. No verdict — the matrix is the deliverable.

## Why

The shootout matrix is the operator's comparison view of coding models: rows
are models, columns are persona shapes (REPL, Audit, and the rest), and each
cell shows how the model performed on that shape. Like every bench artifact,
the matrix is the deliverable and the verdict stays operator-only — the
analysis presents the evidence, and the promotion decision is made by a
human under the promotion policy. Deriving the matrix from the persona-matrix
JSON means it is reproducible from a recorded run rather than hand-assembled.

## Interfaces

The analyzer parses the JSON, groups by model and shape, and renders the
matrix.

## Gotchas

The no-verdict contract is the same as the other analyzers — the matrix
informs, it does not decide.
