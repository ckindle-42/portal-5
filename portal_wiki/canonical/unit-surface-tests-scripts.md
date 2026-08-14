---
id: unit-surface-tests-scripts
kind: mixed
title: "Bench matrix analyzers \u2014 no-verdict comparative scoring"
sources:
- type: code
  path: tests/scripts/*.py
claims: []
confidence: high
tags:
- authored-v1
- tests
created_at: 1785883600.0
updated_at: 1785883600.0
---

The `tests/scripts/*.py` bench analyzers share one contract: parse a results
surface, aggregate it into a comparative per-model matrix, issue no verdict —
promotion under `PROMOTE_POLICY` stays an operator decision. Three scoring
lanes run the same shape: pipeline execution, UAT result rows, game artifacts.

## Why

A description is rhetoric, not evidence — the pipeline lane credits a model
only when its extracted code ran in the sandbox and produced the expected
output. A raw row table defeats comparison — nobody sees which model cleared
which assertion class. A game challenge fails on two independent axes, content
versus a render that boots, so a band is believable only when both pass.

## Interfaces

The analyzers read `tests/UAT_RESULTS.md` rows and saved artifacts, drive each
model through its bench workspace, run execution checks against the sandbox,
and write timestamped matrices to `tests/benchmarks/results/`. Network-gated
scenarios respect `SANDBOX_ALLOW_NETWORK`; the render lane needs `--artifacts`.

## Gotchas

The pipeline lane is strict: a model that runs cleanly but prints the wrong
output fails. `ROW_RE` is regex-locked to the current row format, so a changed
shape drops rows. A render-check without artifacts scores only the static
layer — not a verdict.
