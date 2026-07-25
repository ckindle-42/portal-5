---
id: unit-persona-matrix-ci-ci-vs-local-run-boundary
kind: what
title: "PERSONA_MATRIX_CI \u2014 CI vs. local-run boundary"
sources:
- type: doc
  path: docs/PERSONA_MATRIX_CI.md
  commit: 05e42ec2
  section: CI vs. local-run boundary
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5681589
updated_at: 1784946220.5681589
---

CI runs on a self-hosted runner that has access to the Portal 5 stack.
Public GitHub-hosted runners cannot reach the local pipeline / MLX /
Ollama services. If the self-hosted runner is unavailable, the workflow
queues — it does not fall back to a hosted runner.

The CI run is **non-destructive** by design:
- Sweep results write to `tests/benchmarks/results/...` and are uploaded
  as a workflow artifact (30-day retention) but are **not** auto-committed
- Baselines are updated only by an operator-authored commit
- Failed CI runs comment with the diff summary but do not block local
  development unless the failing run is on a PR
