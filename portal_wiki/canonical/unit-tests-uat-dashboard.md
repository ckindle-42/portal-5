---
id: unit-tests-uat-dashboard
kind: mixed
title: "Tests UAT dashboard \u2014 results aggregation views"
sources:
- type: code
  path: tests/uat_dashboard.py
  commit: 4900007a
last_generated_commit: 4900007a
claims: []
confidence: high
tags:
- authored-v1
- tests
created_at: 1785798828.235564
updated_at: 1785798828.235564
---

`uat_dashboard.py` reads the UAT results markdown (and optionally the
uat_corpus JSONL for trends) and outputs a structured dashboard: section
tables, per-model tables, failing rows, and trend tables, printed to stdout
or written as markdown.

## Why

The UAT results file is a long row table, and "how did this run go overall?"
is not answerable by reading it directly. The dashboard aggregates the rows
into the views an operator actually wants — what passed per section, what
passed per model, what failed, and how the trend moves across corpus runs.
Reading the committed results file (rather than a live service) means the
dashboard is reproducible from any recorded run.

## Interfaces

`_parse_uat_results`, `_parse_corpus_runs`, the table builders, and
`build_dashboard`/`_print_terminal`.

## Gotchas

The dashboard's fidelity depends on the results-file format — a row-shape
change in the UAT results markdown must be reflected in the parser or rows
silently vanish.
