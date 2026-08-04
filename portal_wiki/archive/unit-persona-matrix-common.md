---
id: unit-persona-matrix-common
kind: mixed
title: "Persona matrix common \u2014 shared constants + registry loader"
sources:
- type: code
  path: portal/modules/eval/persona_matrix/_common.py
  commit: 7954fafc
last_generated_commit: baca992c674a3cbb36a619e8f62e7e88b8fccfff
claims: []
confidence: high
tags:
- authored-v1
- eval
- persona-matrix
created_at: 1785796983.60345
updated_at: 1785796983.60345
---

`_common.py` holds the shared constants and helpers for the persona-matrix
harness: the Ollama URL, results directory, request timeout, the audit prompt
and tool definition, and the workspace-registry loader.

## Why

The shared-constants split is what keeps the sweep, the client, and the
loaders from each re-deriving the same environment facts and drifting apart.
`SYSTEM_PROMPT_CAP_CHARS` and `REQUEST_TIMEOUT` are tuning values that must
be identical everywhere a matrix cell runs, and `EVICT_BACKOFF_S` is the
cooldown between model evictions — a memory-discipline constant that belongs
in one place because every model swap in a sweep depends on it. The workspace
registry loader here is how the package resolves workspace module structures
without each module importing its own copy.

## Interfaces

`OLLAMA_URL`, `RESULTS_DIR`, `REQUEST_TIMEOUT`, `SYSTEM_PROMPT_CAP_CHARS`,
`EVICT_BACKOFF_S`, `AUDIT_PROMPT`, and `AUDIT_TOOL_DEFINITION` are the shared
constants; `_load_workspace_modules(workspace_id)` resolves the workspace's
module shape.

## Gotchas

`RESULTS_DIR` points at `tests/benchmarks/results` — the committed-output
area — so a matrix run writes where the bench reports are expected to land.
