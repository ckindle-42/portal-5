---
id: unit-persona-matrix-ci-out-of-scope-for-ci
kind: what
title: "PERSONA_MATRIX_CI \u2014 Out of scope for CI"
sources:
- type: code
  path: tests/persona_matrix_diff.py
- type: code
  path: tests/portal5_acceptance_v6.py
- type: code
  path: tests/acceptance/runner.py
- type: code
  path: portal/modules/eval/persona_matrix/_common.py
- type: code
  path: portal/modules/eval/persona_matrix/cli.py
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.569539
updated_at: 1784946220.569539
---

Three workloads are deliberately outside the persona-matrix CI gate. First, throughput comparisons: `bench_tps` (in `tests/benchmarks/`) owns TPS and latency, while the matrix driver records a `tps` field per scenario only as context — its pass/fail decision and the baseline diff use assertion outcomes exclusively, since `persona_matrix_diff.py` computes PASS-rate as PASS over PASS+WARN+FAIL and never reads throughput. Second, pipeline routing: `portal5_acceptance_v6.py` owns routing validation through section `S3a` (Ollama workspace routing, delegating to `tests/acceptance/runner.py`), whereas the matrix pins a model directly in the chat request via `_chat_direct` to measure raw model behavior. The former `S3b` MLX routing section was retired with the MLX proxy in `3a0c58e`.

Third, unregistered workspaces: the CLI derives its `--workspace` choices from the keys of `WORKSPACE_REGISTRY`, and `_load_workspace_modules` raises a hard exit if a requested workspace is not registered, so a workspace must be added to the registry before CI can sweep it. Nothing in the driver discovers workspaces dynamically.

## Why

The scope line exists because each instrument measures something different and mixing them produces misleading signals: routing belongs to acceptance because it exercises the intent classifier and routing chain, throughput belongs to bench because it needs controlled warm and cold load, and the matrix measures only behavioral compliance of a pinned model. Keeping the division explicit in the registry and driver makes what CI does not check as checkable as what it does.
