---
id: unit-tests-persona-matrix-diff
kind: mixed
title: "Tests persona-matrix diff \u2014 gated report comparison"
sources:
- type: code
  path: tests/persona_matrix_diff.py
  commit: 4900007a
last_generated_commit: 4900007a
claims: []
confidence: high
tags:
- authored-v1
- tests
created_at: 1785798798.5716171
updated_at: 1785798798.5716171
---

`persona_matrix_diff.py` diffs two persona-matrix reports — a baseline and a
new run — and reports per-cell regressions, improvements, and added/removed
cells, with exit codes so it can gate a promotion.

## Why

The matrix produces a report per run, and the operator's question is "did
this model get better or worse since the baseline?" The diff answers it with
exit codes: a regression past the threshold fails, so the diff can gate
whether a model is promoted. Deriving regressions and improvements from the
cell pass-rates (rather than eyeballing two tables) is what makes the
comparison a machine decision an operator can trust.

## Interfaces

`compute_regressions`, `compute_improvements`, `added_removed_cells`,
`_cell_pass_rate`, and `main` with the threshold and JSON flags.

## Gotchas

The threshold is the sensitivity control — a threshold too low flags noise as
a regression, too high hides a real one. The default exists, and the CLI lets
an operator tune it.
