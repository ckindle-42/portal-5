---
id: unit-persona-matrix-sweep
kind: mixed
title: "Persona matrix sweep \u2014 cell grid with memory discipline"
sources:
- type: code
  path: portal/modules/eval/persona_matrix/sweep.py
  commit: 7954fafc
last_generated_commit: 7954fafc
claims: []
confidence: high
tags:
- authored-v1
- eval
- persona-matrix
created_at: 1785797000.90514
updated_at: 1785797000.90514
---

`sweep.py` is the sweep orchestration: `run_cell` runs every applicable
scenario from a workspace fixture against one (persona, model) pair and
aggregates assertion outcomes, and `run_sweep` iterates the cell grid for a
workspace, loading and evicting models one at a time per the
memory-discipline contract.

## Why

The one-model-at-a-time loading discipline is the core constraint the sweep
exists to honour: loading two candidate models simultaneously risks eviction
mid-cell, which corrupts the very comparison the matrix is measuring. The
cell/aggregate split is what makes the output honest — a cell collects raw
assertion outcomes and `run_sweep` folds them into the PASS/WARN/FAIL summary
per persona-model pair that `render` prints.

## Interfaces

`run_cell` runs the fixture scenarios for one pair and returns the aggregated
summary; `run_sweep` builds the cell grid, sequences the model loads with
eviction cooldown, and returns the report dict of cells.

## Gotchas

A sweep is a long-running, sequential job by design (one model resident at a
time) — the task's own discipline forbids running two sweeps concurrently,
because VRAM contention would make both sets of numbers meaningless.
