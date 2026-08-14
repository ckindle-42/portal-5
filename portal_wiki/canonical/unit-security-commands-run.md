---
id: unit-security-commands-run
kind: mixed
title: "Security bench runner \u2014 dual-pass execution with serial chain phase"
sources:
- type: code
  path: portal/modules/security/core/commands/run.py
  commit: 5b73259d
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- commands
- bench
created_at: 1785795362.8310652
updated_at: 1785795362.8310652
---

`run_bench` is the dual-pass security bench executor extracted from the CLI: a
theory pass where the model sees no tools and is scored on full prose, an
execution pass (for `EXECUTION_WORKSPACES`) where tools are enabled and tool
call sequences are scored, and an optional multi-model execution chain whose
composite score lands in `chain_exec_composite`. It is the largest piece of
the security bench's command surface and the only one that actually talks to
the pipeline and the chain.

## Why

The two-phase split exists because the two passes put different load on
Ollama. Phase 1 (theory + exec) is parallelisable across workspace/prompt
tuples because each is an independent task bounded by the pipeline's
per-workspace semaphore and Ollama's `OLLAMA_NUM_PARALLEL`. Phase 2 (the chain
batch) stays serial because the warm-up logic needs surgical control over
Ollama's `OLLAMA_MAX_LOADED_MODELS` slots — the regression this design
prevents was chain models being evicted mid-run by pipeline workspace models
loaded in Phase 1. That is why `chain_pending` is collected during Phase 1 and
executed only after it finishes, and why a chain-only mode skips Phase 1
entirely. The `_emit_parallel_preflight` banner warns when the configured slot
count is below the four a `purpleteam-deep` chain needs.

## Interfaces

`run_bench(...)` takes the workspace roster, prompt keys, and a `BenchConfig`,
plus the phase switches (`exec_eval`, `exec_chain_models`, `blue_defender_model`,
`lab_exec`, `direct_theory_model`) and returns a deterministic sorted result
list. `_workspace_category` classifies a workspace as redteam, blueteam,
purpleteam, or general for prompt-matching. `_print_summary` and
`_print_intake_summary` render the result tables.

## Gotchas

The pipeline call functions are imported lazily inside `run_bench` to avoid a
circular dependency with the package facade, and are tolerated as `None` in
chain-only mode. A blueteam workspace skips redteam-category prompts and vice
versa — the category cross-check is the prompt/workspace fit filter.
