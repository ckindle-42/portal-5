---
id: unit-persona-matrix-init
kind: mixed
title: "Persona matrix \u2014 per-(persona, model) coverage harness"
sources:
- type: code
  path: portal/modules/eval/persona_matrix/__init__.py
  commit: 7954fafc
last_generated_commit: 7954fafc
claims: []
confidence: high
tags:
- authored-v1
- eval
- persona-matrix
created_at: 1785796977.8651688
updated_at: 1785796977.8651688
---

The persona_matrix package is the per-(persona, model) coverage matrix
harness: it sweeps every persona across every candidate model and records
which personas pass, warn, or fail on which model, so coverage gaps are
visible as a matrix instead of a list. It was extracted from the monolithic
bench tooling into its own package.

## Why

A matrix sweep answers a question no single bench run can: is every persona
covered by *some* model, and which models are redundant? The package splits
the concern cleanly — loaders read the config, ollama_client talks to the
backend directly, sweep drives the cell grid, render prints the table — so a
persona-matrix run is reproducible and its output is comparable across runs.

## Interfaces

`cli` is the entry point, `loaders` reads backends/personas, `ollama_client`
is the raw backend client, `sweep` runs cells and the full grid, `render`
prints the matrix, and `_common` holds shared constants and registry loading.
