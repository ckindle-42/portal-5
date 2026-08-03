---
id: unit-persona-matrix-cli
kind: mixed
title: "Persona matrix CLI \u2014 sweep entry point"
sources:
- type: code
  path: portal/modules/eval/persona_matrix/cli.py
  commit: 7954fafc
last_generated_commit: 7954fafc
claims: []
confidence: high
tags:
- authored-v1
- eval
- persona-matrix
created_at: 1785797009.962742
updated_at: 1785797009.962742
---

`cli.py` is the persona-matrix entry point: it parses the sweep arguments
and drives the run, printing the matrix and writing the report.

## Why

The CLI is what makes the harness re-runnable: an operator invokes the sweep
with the workspace, persona set, and options, and gets the matrix without
touching Python. Keeping argument parsing separate from the sweep logic
matches the package's split — `cli` is the thin shell, `sweep` is the work.

## Interfaces

`parse_args` builds the argparse surface (workspace, persona slugs, dry-run,
output options) and `main` runs the sweep and renders the result.

## Gotchas

The CLI accepts a dry-run flag so an operator can validate the plan (which
cells would run) before committing to a long sequential sweep.
