---
id: unit-tests-scripts-cc-matrix
kind: mixed
title: "CC-01 challenge matrix \u2014 comparative shootout aggregator"
sources:
- type: code
  path: tests/scripts/cc_challenge_matrix.py
  commit: dc13b2d5
last_generated_commit: dc13b2d5
claims: []
confidence: high
tags:
- authored-v1
- tests
- scripts
- bench
created_at: 1785796167.7856152
updated_at: 1785796167.7856152
---

The CC-01 challenge shootout matrix reads the challenge section rows of the
UAT results markdown (test ids `CC-01-*`, `BT-01-*`, `EX-01-*`) and emits a
comparative capability matrix: one row per model, assertion pass-fraction,
status, and elapsed time. It is the same contract as the coding shootout
analyzer — the matrix is the deliverable, no verdict is issued.

## Why

The challenge shootout produces raw UAT result rows, and a row table is not a
comparative view — a human reading sixty rows cannot see which model passed
which assertion class without aggregation. This script turns the rows into a
per-model pass-fraction matrix so the comparison is visible at a glance. The
no-verdict contract matters because these matrices feed promotion decisions
that must remain operator-only under `PROMOTE_POLICY` — the script presents
the evidence, it does not cast the vote.

## Interfaces

`ROW_RE` is the parser for the challenge-row format; `main` reads
`tests/UAT_RESULTS.md`, groups the rows by model, computes pass-fractions,
and writes a timestamped comparative matrix to `tests/benchmarks/results/`.

## Gotchas

The parser is regex-locked to the exact UAT row format (`CC|BT|EX-01` ids) —
if the results markdown changes its row shape, the regex must change with it
or the matrix silently loses rows.
