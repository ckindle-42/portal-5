---
id: unit-surface-persona-matrix
kind: mixed
title: "Persona-matrix harness \u2014 per-persona x per-model coverage sweep"
sources:
- type: code
  path: portal/modules/eval/persona_matrix/*.py
last_generated_commit: 22007054d6cba73357ea3c5d7d7c97f5c252d7dc
claims: []
confidence: high
tags:
- authored-v1
- eval
- persona-matrix
created_at: 1785884600.0
updated_at: 1785884600.0
---

The persona-matrix harness is the eval package's per-(persona, model) coverage sweep: which candidates are redundant, and whether every persona is covered by some model. It resolves a workspace's personas and model chain, runs applicable fixture scenarios per pair, and folds assertion outcomes into a PASS/WARN/FAIL cell grid.

## Why

A matrix is the honest shape for coverage because a routing bug and a model-capability gap look identical through the pipeline; the client pins the model in the raw request, so the harness measures raw model behaviour for bench purposes only, never user traffic. Loading candidates together risks a mid-cell eviction that corrupts the comparison; the one-resident-model discipline, eviction cooldown, and scheduling size estimate are part of the same contract.

## Interfaces

`parse_args` builds the argparse surface; `run_sweep` resolves personas and the model chain, sequences loads, and returns the report dict; `run_cell` runs a fixture scenario set for one pair; `render_matrix_table` prints the grid; `_chat_direct` probes the backend; `run_audit_tools` verifies per-model tool-call support.

## Gotchas

Because the client bypasses the pipeline, it also bypasses its security and tool gating — bench harnesses only. A sweep is sequential by design and must not run concurrently; the dry-run flag validates the plan first.
