---
id: unit-acceptance-results
kind: mixed
title: "Acceptance results \u2014 run summary writer"
sources:
- type: code
  path: tests/acceptance/results.py
  commit: e75dddd2
last_generated_commit: e75dddd2
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799706.479161
updated_at: 1785799706.479161
---

`results.py` writes the acceptance results summary for a run.

## Why

Each acceptance run needs a durable summary (outcomes, timing, git sha)
that the dashboard and the operator read, in the same shape the other
acceptance packages produce.

## Interfaces

The result writer producing the run summary.

## Gotchas

The git sha in the record ties the result to the code state that produced it.
