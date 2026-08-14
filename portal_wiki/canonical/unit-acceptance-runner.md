---
id: unit-acceptance-runner
kind: mixed
title: "Acceptance runner \u2014 section sequencing"
sources:
- type: code
  path: tests/acceptance/runner.py
  commit: a88ad75b
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799710.136381
updated_at: 1785799710.136381
---

`runner.py` orchestrates the acceptance sections: it defines the S-section
sequence, parses the selection, and runs the chosen sections in order with
the skip rules.

## Why

Acceptance sections have dependencies and ordering constraints, and the
runner is the sequencing layer that enforces them. Keeping orchestration
separate from the sections means a section change does not touch the run
flow, and the skip logic is centralised rather than embedded per section.

## Interfaces

The section functions, the selection parser, and the run orchestrator.

## Gotchas

Order matters — a section that depends on a prior section's setup produces a
misleading failure if run out of order, so the runner enforces the canonical
sequence.
