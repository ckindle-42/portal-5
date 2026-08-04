---
id: unit-persona-matrix-render
kind: mixed
title: "Persona matrix render \u2014 PASS/WARN/FAIL grid"
sources:
- type: code
  path: portal/modules/eval/persona_matrix/render.py
  commit: 7954fafc
last_generated_commit: 7954fafc
claims: []
confidence: high
tags:
- authored-v1
- eval
- persona-matrix
created_at: 1785797006.6333282
updated_at: 1785797006.6333282
---

`render.py` turns the persona-matrix report into the console table: a
persona-per-row, model-per-column grid where each cell shows the PASS/WARN/FAIL
counts for that pair.

## Why

A report dict of cells is not a coverage answer — the human question is "at a
glance, which personas have a passing model and which models cover nothing",
and that is a matrix, not a list. The renderer collapses model ids to short
names and prints `P{pass}/W{warn}/F{fail}` per cell so a gap (a column of
dashes) is visible immediately. An empty report renders "(no cells)" rather
than a broken table.

## Interfaces

`render_matrix_table(report)` returns the markdown-ish table string built
from the report's cells, de-duplicating the model columns by
(backend, model) pair.

## Gotchas

The table width grows with the model count — a wide sweep produces a very
wide table, which is a presentation limit, not a correctness issue.
